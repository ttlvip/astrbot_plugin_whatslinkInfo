"""
AstrBot 插件：whatslink.info 磁链解析器
- 自动识别消息中的 magnet: 链接
- 调用 https://whatslink.info/api/v1/link?url=... 获取资源信息
- 支持插件配置：timeout（毫秒），useForward（合并转发，QQ/OneBot），showScreenshot（显示截图）
- 包发送成功的反 QQ 风控方案
"""

from __future__ import annotations

import re
import aiohttp
import asyncio
import time
from typing import List
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Node, Nodes
import io

# 导入动态噪声生成器
from .noise_generator import generate_noise_variants, generate_edge_variants

try:
    from PIL import Image as PImage

    HAS_PILLOW = True
except ImportError:
    logger.warning("Pillow 库缺失")
    HAS_PILLOW = False


MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+)", re.IGNORECASE)
BTIH_RE = re.compile(r"btih:([A-Za-z0-9]+)", re.IGNORECASE)
API_URL = "https://whatslink.info/api/v1/link"


def _human_readable_size(num: int) -> str:
    """将字节数格式化为人类可读的字符串（中文单位）。"""
    if num is None:
        return "未知"
    try:
        num = int(num)
    except Exception:
        return str(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f}{unit}"
        num /= 1024
    return f"{num:.2f}PB"


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_btih(magnet: str) -> str:
    match = BTIH_RE.search(magnet or "")
    return match.group(1).lower() if match else "unknown"


def _build_edge_ratio_levels(max_ratio: float) -> List[float]:
    ratio = max(0.01, min(0.2, max_ratio))
    levels = [ratio * 0.5, ratio * 0.75, ratio]
    cleaned: List[float] = []
    for r in levels:
        r = max(0.01, min(0.2, r))
        if not cleaned or abs(r - cleaned[-1]) > 1e-4:
            cleaned.append(r)
    return cleaned


@register(
    "astrbot_plugin_whatslinkInfo",
    "Zhalslar",
    "磁链解析插件（whatslink.info）",
    "1.0.0",
)
class WhatslinkPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.context = context
        self.config = config

    async def initialize(self):
        """异步初始化（可选）"""

    async def _call_api(self, url: str, timeout_ms: int = 10000) -> dict | None:
        """调用 whatslink.info API 并返回 JSON，失败返回 None。"""
        t0 = time.time()
        q = {"url": url}
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000 if timeout_ms else None)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(API_URL, params=q, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.error(f"whatslink.info 返回状态码: {resp.status}")
                        return None
                    data = await resp.json()
                    logger.debug(f"[Timer] API请求耗时: {time.time() - t0:.3f}s")
                    return data
        except asyncio.TimeoutError:
            logger.warning("whatslink.info 请求超时")
            return None
        except Exception as e:
            logger.error(f"whatslink.info 请求出错: {e}")
            return None

    async def _stitch_images(self, images: List[PImage.Image]) -> bytes | None:
        """将已下载的图片对象拼接为长图，返回 bytes。"""
        t0 = time.time()
        if not HAS_PILLOW or not images:
            return None
        try:
            # 拼接图片
            widths, heights = zip(*(i.size for i in images))
            max_width = max(widths)
            total_heights = sum(heights)

            # 创建新图片
            new_image = PImage.new("RGB", (max_width, total_heights), (255, 255, 255))

            y_offset = 0
            for im in images:
                new_image.paste(im, (0, y_offset))
                y_offset += im.size[1]

            output = io.BytesIO()
            new_image.save(output, format="JPEG", quality=85)
            logger.debug(f"[Timer] 图片拼接耗时: {time.time() - t0:.3f}s")
            return output.getvalue()

        except Exception as e:
            logger.warning(f"拼接图片失败: {e} (耗时: {time.time() - t0:.3f}s)")
            return None

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，自动识别并解析磁链（magnet:）。

        行为：
        - 当消息中包含 magnet 链接时，触发解析流程。
        - 先发送一条“解析中...”提示（平台不一定支持撤回，本插件会尽量减少噪音）。
        - 请求 API，格式化并发送解析结果；根据配置可发送合并转发（QQ/OneBot）。
        - 风控降级策略：合并转发+原图 -> 合并转发+拼接图 -> 合并转发+边缘图案 -> 合并转发+动态噪声(逐级增强) -> 纯文本
        """
        text = event.get_message_str() or ""
        if not text:
            return

        magnets = MAGNET_RE.findall(text)
        if not magnets:
            return

        # 读取配置
        timeout = int(self.config.get("timeout", 10000))
        use_forward = bool(self.config.get("useForward", True))
        show_screenshot = bool(self.config.get("showScreenshot", True))
        max_stitch_count = int(self.config.get("max_stitch_count", 4))
        edge_ratio_max = _safe_float(self.config.get("edge_ratio", 0.06), 0.06)
        save_failed_images = bool(self.config.get("save_failed_images", True))
        failed_images_dir = str(self.config.get("failed_images_dir", "failed_images"))

        edge_ratio_levels = _build_edge_ratio_levels(edge_ratio_max)
        edge_variants_per_level = 1
        edge_sides = "all"
        noise_variants_per_strategy = 2
        noise_strategies = ["minimal", "balanced", "aggressive"]

        logger.debug(f"[Config] timeout={timeout}, use_forward={use_forward}, show_screenshot={show_screenshot}, max_stitch_count={max_stitch_count}")
        logger.debug(
            f"[Config] edge_ratio_max={edge_ratio_max}, edge_ratio_levels={edge_ratio_levels}"
        )
        logger.debug(
            f"[Config] edge_variants_per_level={edge_variants_per_level}, noise_variants_per_strategy={noise_variants_per_strategy}"
        )
        logger.debug(
            f"[Config] save_failed_images={save_failed_images}, failed_images_dir={failed_images_dir}"
        )
        logger.debug(f"[Config] raw config: {self.config}")

        # 先发"解析中"的提示（尽量简短）
        try:
            yield event.plain_result("解析磁链中...")
        except Exception:
            # 发送失败不影响主流程
            pass

        # results_to_send: List[MessageEventResult] = []

        for m in magnets:
            api_ret = await self._call_api(m, timeout_ms=timeout)
            if not api_ret:
                try:
                    await self.context.send_message(
                        event.unified_msg_origin,
                        MessageEventResult().message(f"解析失败: {m}"),
                    )
                except Exception:
                    pass
                continue

            # 解析响应字段，按 API 文档处理
            err = api_ret.get("error") or ""
            if err:
                try:
                    await self.context.send_message(
                        event.unified_msg_origin,
                        MessageEventResult().message(f"解析失败: {err}"),
                    )
                except Exception:
                    pass
                continue

            name = api_ret.get("name", "未知名称")
            size = api_ret.get("size")
            count = api_ret.get("count")
            file_type = api_ret.get("file_type", api_ret.get("type", ""))
            screenshots = api_ret.get("screenshots", []) or []

            # 构建要显示的文本
            header = f"名称: {name}\n文件类型: {file_type}\n文件数量: {count}\n总大小: {size} ({_human_readable_size(size)})\n"

            # 如果需要显示截图，准备所有截图 URL 列表（按 API 返回顺序）。
            shots: List[str] = []
            if (
                show_screenshot
                and isinstance(screenshots, list)
                and len(screenshots) > 0
            ):
                for s in screenshots:
                    url = s.get("screenshot")
                    if url:
                        shots.append(url)

            # === 资源预加载与并行计算管理 ===

            # 缓存下载好的图片对象 (PIL Image)，供多图发送和拼接使用
            downloaded_images_cache: List[PImage.Image] | None = None
            task_download: asyncio.Task | None = None

            task_stitch: asyncio.Task | None = None
            task_noise_variants: dict[str, asyncio.Task] = {}
            task_edge_variants: dict[int, asyncio.Task] = {}

            # 1. 图片下载
            async def _download_images() -> List[PImage.Image]:
                nonlocal downloaded_images_cache
                if downloaded_images_cache is not None:
                    return downloaded_images_cache

                t0 = time.time()
                imgs = []
                # 限制下载数量，取 max_stitch_count 和 9 (多图发送上限) 的较小值，避免超出限制
                limit = min(max_stitch_count, 9)
                target_urls = shots[:limit]

                try:
                    async with aiohttp.ClientSession() as session:
                        tasks = [session.get(url, timeout=10) for url in target_urls]
                        responses = await asyncio.gather(*tasks, return_exceptions=True)
                        for resp in responses:
                            if not isinstance(resp, Exception) and resp.status == 200:
                                data = await resp.read()
                                try:
                                    if HAS_PILLOW:
                                        img = PImage.open(io.BytesIO(data))
                                        img.load()  # 强制加载到内存
                                        imgs.append(img)
                                except Exception:
                                    pass
                            if hasattr(resp, "close"):
                                resp.close()
                except Exception as e:
                    logger.warning(f"图片下载失败: {e}")

                logger.debug(
                    f"[Timer] 图片下载耗时: {time.time() - t0:.3f}s, 成功: {len(imgs)}"
                )
                downloaded_images_cache = imgs
                return imgs

            def _ensure_download_task():
                nonlocal task_download
                if not task_download and shots:
                    task_download = asyncio.create_task(_download_images())
                return task_download

            # 2. 异步生成动态噪声变体
            async def _generate_noise_variants(strategy: str):
                nonlocal task_noise_variants
                if not task_noise_variants.get(strategy) and shots and HAS_PILLOW:
                    task_noise_variants[strategy] = asyncio.create_task(
                        _run_noise_generation(strategy)
                    )
                return task_noise_variants.get(strategy)

            async def _run_noise_generation(strategy: str):
                """生成多个动态噪声变体"""
                stitch_t = task_stitch
                if not stitch_t:
                    return []

                # 等待拼接图完成
                stitched_bytes = await stitch_t
                if not stitched_bytes:
                    return []

                # 生成指定数量的噪声变体
                t0 = time.time()
                # 使用内部固定数量和策略
                variant_count = noise_variants_per_strategy
                variants = generate_noise_variants(
                    stitched_bytes, count=variant_count, strategy=strategy
                )
                logger.debug(
                    f"[Timer] 动态噪声生成耗时: {time.time() - t0:.3f}s, 变体数: {len(variants)}, strategy={strategy}"
                )
                return variants

            # 2.5 异步生成边缘黑色图案变体
            async def _generate_edge_variants(level_index: int):
                nonlocal task_edge_variants
                if level_index < 0 or level_index >= len(edge_ratio_levels):
                    return None
                if not task_edge_variants.get(level_index) and shots and HAS_PILLOW:
                    ratio = edge_ratio_levels[level_index]
                    task_edge_variants[level_index] = asyncio.create_task(
                        _run_edge_generation(ratio)
                    )
                return task_edge_variants.get(level_index)

            async def _run_edge_generation(ratio: float):
                """生成边缘黑色图案变体"""
                stitch_t = task_stitch
                if not stitch_t:
                    return []

                stitched_bytes = await stitch_t
                if not stitched_bytes:
                    return []

                t0 = time.time()
                variant_count = edge_variants_per_level
                variants = generate_edge_variants(
                    stitched_bytes,
                    count=variant_count,
                    edge_ratio=ratio,
                    edge_sides=edge_sides,
                )
                logger.debug(
                    f"[Timer] 边缘图案生成耗时: {time.time() - t0:.3f}s, 变体数: {len(variants)}, ratio={ratio}"
                )
                return variants

            # 3. 启动/获取 拼接任务 (依赖下载任务)
            async def _run_stitch():
                imgs = await _ensure_download_task()
                if not imgs:
                    return None
                # 仅使用前 max_stitch_count 张进行拼接
                return await self._stitch_images(imgs[:max_stitch_count])

            def _ensure_stitch_task():
                nonlocal task_stitch
                if not task_stitch and shots and HAS_PILLOW:
                    task_stitch = asyncio.create_task(_run_stitch())
                return task_stitch

            def _trigger_precalc():
                """预计算：在尝试发送原拼接图时，预生成边缘图案/噪声变体"""
                if not HAS_PILLOW or not shots:
                    return
                if edge_ratio_levels:
                    _generate_edge_variants(0)
                if noise_strategies:
                    _generate_noise_variants(noise_strategies[0])

            async def _send(use_fwd: bool, mode: str) -> bool:
                """使用指定策略发送消息。
                Args:
                    use_fwd: 是否使用转发消息模式
                    mode: 发送模式
                        - 'multi_images': 发送多张独立图片
                        - 'stitched_image': 发送拼接图片
                        - 'dynamic_noise:<strategy>:<index>': 发送指定策略的噪声变体
                        - 'edge_variant:<level_index>:<index>': 发送指定级别的边缘图案变体
                Returns:
                    bool: True/False
                Raises:
                    内部捕获所有异常并记录日志，不向外抛出
                """
                t0 = time.time()
                strategy_name = f"[Forward={use_fwd}, Mode={mode}]"
                logger.info(f"尝试发送策略: {strategy_name}")

                try:
                    chain = [Plain(header)]

                    if mode == "multi_images" and shots:
                        # 等待下载完成
                        imgs = await _ensure_download_task()
                        if imgs:
                            for img in imgs:
                                # 将 PIL Image 转回 bytes 发送
                                output = io.BytesIO()
                                img.save(output, format="JPEG")
                                chain.append(Image.fromBytes(output.getvalue()))
                        else:
                            logger.warning(f"策略 {strategy_name} 跳过: 图片下载失败")
                            return False

                    elif mode == "stitched_image":
                        t = _ensure_stitch_task()
                        img_data = await t if t else None
                        if img_data:
                            chain.append(Image.fromBytes(img_data))
                            # 关键点：在尝试发送原拼接图时，立即触发后续噪声变体的计算
                            _trigger_precalc()
                        else:
                            logger.warning(f"策略 {strategy_name} 跳过: 图片拼接失败")
                            return False

                    elif mode.startswith("dynamic_noise"):
                        strategy = "balanced"
                        variant_index = 0
                        if ":" in mode:
                            parts = mode.split(":")
                            if len(parts) >= 3:
                                strategy = parts[1] or "balanced"
                                try:
                                    variant_index = int(parts[2])
                                except Exception:
                                    variant_index = 0
                        else:
                            try:
                                variant_index = int(mode.split("_")[-1])
                            except Exception:
                                variant_index = 0

                        # 等待噪声变体生成完成
                        noise_task = await _generate_noise_variants(strategy)
                        if noise_task:
                            variants = await noise_task
                            if variant_index < len(variants):
                                img_data = variants[variant_index]
                                chain.append(Image.fromBytes(img_data))
                            else:
                                logger.warning(f"策略 {strategy_name} 跳过: 噪声变体索引超出范围")
                                return False
                        else:
                            logger.warning(f"策略 {strategy_name} 跳过: 噪声生成任务未启动")
                            return False
                    elif mode.startswith("edge_variant"):
                        level_index = 0
                        variant_index = 0
                        if ":" in mode:
                            parts = mode.split(":")
                            if len(parts) >= 3:
                                try:
                                    level_index = int(parts[1])
                                except Exception:
                                    level_index = 0
                                try:
                                    variant_index = int(parts[2])
                                except Exception:
                                    variant_index = 0
                        else:
                            try:
                                variant_index = int(mode.split("_")[-1])
                            except Exception:
                                variant_index = 0

                        edge_task = await _generate_edge_variants(level_index)
                        if edge_task:
                            variants = await edge_task
                            if variant_index < len(variants):
                                img_data = variants[variant_index]
                                chain.append(Image.fromBytes(img_data))
                            else:
                                logger.warning(f"策略 {strategy_name} 跳过: 边缘变体索引超出范围")
                                return False
                        else:
                            logger.warning(f"策略 {strategy_name} 跳过: 边缘图案生成任务未启动")
                            return False

                    mer = MessageEventResult()
                    if use_fwd and event.get_platform_name() in (
                        "aiocqhttp",
                        "qq",
                        "qq_official",
                        "onebot",
                    ):
                        node = Node(
                            content=chain,
                            name=event.get_sender_name() or "AstrBot",
                            uin=str(event.get_sender_id()),
                        )
                        mer.chain = [Nodes(nodes=[node])]
                    else:
                        mer.chain = chain

                    await self.context.send_message(event.unified_msg_origin, mer)
                    logger.info(
                        f"策略 {strategy_name} 发送成功 (耗时: {time.time() - t0:.3f}s)"
                    )
                    return True
                except Exception as e:
                    logger.warning(
                        f"策略 {strategy_name} 发送失败: {e} (耗时: {time.time() - t0:.3f}s)"
                    )
                    return False

            # === 执行发送策略 ===

            # 无 Pillow 时使用原方式 
            async def _send_fallback_url_mode() -> bool:
                """使用 Image.fromURL() 发送。"""
                try:
                    mer = MessageEventResult()
                    content = [Plain(header)]
                    for url in shots:
                        content.append(Image.fromURL(url))

                    if use_forward and event.get_platform_name() in (
                        "aiocqhttp",
                        "qq",
                        "qq_official",
                        "onebot",
                    ):
                        node = Node(
                            content=content,
                            name=event.get_sender_name() or "AstrBot",
                            uin=str(event.get_sender_id()),
                        )
                        mer.chain = [Nodes(nodes=[node])]
                    else:
                        mer.chain = content

                    await self.context.send_message(event.unified_msg_origin, mer)
                    return True
                except Exception as e:
                    logger.warning(f"发送解析结果失败: {e}")
                    return False

            # 无 Pillow: 使用 URL 模式 (兼容原逻辑)
            if not HAS_PILLOW:
                if not await _send_fallback_url_mode():
                    # 保底纯文本
                    await _send(use_fwd=False, mode="text_only")
                continue

            # 无截图：直接发送纯文本
            if not shots:
                logger.info("无截图，直接发送纯文本")
                await _send(use_fwd=use_forward, mode="text_only")
                continue

            # 有 Pillow + 有截图: 启动后台任务 下载 -> 拼接 -> 干扰图生成
            _ensure_download_task()
            _ensure_stitch_task()
            _trigger_precalc()

            # 标记是否已成功发送消息
            sent_success = False

            def _cleanup():
                tasks = [task_download, task_stitch]
                tasks.extend(task_edge_variants.values())
                tasks.extend(task_noise_variants.values())
                for t in tasks:
                    if t and not t.done():
                        t.cancel()

            async def _save_failed_images(magnet: str, name_text: str):
                if not save_failed_images:
                    return

                stitched_bytes = None
                edge_variants: dict[int, List[bytes]] = {}
                noise_variants: dict[str, List[bytes]] = {}

                if task_stitch:
                    try:
                        stitched_bytes = await task_stitch
                    except Exception as e:
                        logger.warning(f"读取拼接图失败: {e}")
                if task_edge_variants:
                    for level_index, task in task_edge_variants.items():
                        try:
                            variants = await task
                            if variants:
                                edge_variants[level_index] = variants
                        except Exception as e:
                            logger.warning(f"读取边缘变体失败: level={level_index}, {e}")
                if task_noise_variants:
                    for strategy, task in task_noise_variants.items():
                        try:
                            variants = await task
                            if variants:
                                noise_variants[strategy] = variants
                        except Exception as e:
                            logger.warning(f"读取噪声变体失败: {strategy}, {e}")

                if not stitched_bytes and not edge_variants and not noise_variants:
                    return

                base_dir = Path(failed_images_dir)
                if not base_dir.is_absolute():
                    base_dir = Path(__file__).resolve().parent / base_dir

                ts = time.time()
                timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
                millis = int((ts % 1) * 1000)
                folder_name = f"{timestamp}_{millis:03d}_{_extract_btih(magnet)}"
                target_dir = base_dir / folder_name

                def _write_files():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    if stitched_bytes:
                        (target_dir / "stitched.jpg").write_bytes(stitched_bytes)
                    for level_index, variants in edge_variants.items():
                        ratio = None
                        if level_index < len(edge_ratio_levels):
                            ratio = edge_ratio_levels[level_index]
                        ratio_tag = f"{ratio:.3f}" if ratio is not None else str(level_index)
                        for i, img in enumerate(variants):
                            (target_dir / f"edge_{ratio_tag}_{i + 1}.jpg").write_bytes(img)
                    for strategy, variants in noise_variants.items():
                        for i, img in enumerate(variants):
                            (target_dir / f"noise_{strategy}_{i + 1}.jpg").write_bytes(img)
                    meta = f"magnet={magnet}\nname={name_text}\n"
                    (target_dir / "meta.txt").write_text(meta, encoding="utf-8")

                try:
                    await asyncio.to_thread(_write_files)
                    logger.info(f"已保存风控失败图片: {target_dir}")
                except Exception as e:
                    logger.warning(f"保存风控失败图片失败: {e}")

            # 1. 合并转发 + 多张原图
            if use_forward:
                if await _send(use_fwd=True, mode="multi_images"):
                    _cleanup()
                    continue

            # 2. 合并转发 + 拼接长图
            if use_forward:
                if await _send(use_fwd=True, mode="stitched_image"):
                    sent_success = True
                    _cleanup()
                    continue

            # 3. 合并转发 + 边缘黑色图案变体
            if use_forward and not sent_success:
                for level_index in range(len(edge_ratio_levels)):
                    for i in range(edge_variants_per_level):
                        if await _send(
                            use_fwd=True, mode=f"edge_variant:{level_index}:{i}"
                        ):
                            _cleanup()
                            sent_success = True
                            break
                    if sent_success:
                        break

            # 4. 合并转发 + 动态噪声变体（自动逐级增强）
            if use_forward and not sent_success:  # 只有在之前策略都失败时才尝试
                for strategy in noise_strategies:
                    for i in range(noise_variants_per_strategy):
                        if await _send(use_fwd=True, mode=f"dynamic_noise:{strategy}:{i}"):
                            _cleanup()
                            sent_success = True
                            break
                    if sent_success:
                        break

            # 5. 纯文本保底（只有当所有噪声策略都失败时）
            if not use_forward or not sent_success:
                if use_forward and not sent_success:
                    await _save_failed_images(m, name)
                await _send(use_fwd=False, mode="text_only")
            _cleanup()

    async def terminate(self):
        """插件被卸载/停用时调用（可选）"""
        return
