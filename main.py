"""
AstrBot 插件：whatslink.info 磁链解析器 (v2.0.0)

================================================================================
                              功  能  概  述
================================================================================
• 自动检测消息中的磁力链接（magnet:?xt=urn:btih:...），调用 whatslink.info API
  获取资源的预览信息（名称、文件数量、总大小、截图等），并格式化回复。

• 截图处理：支持将多张截图垂直拼接为一张图片；支持对截图进行高斯模糊处理。

• 合并转发：在 QQ / OneBot 平台下，可选将解析结果以合并转发形式发送。

• 命令系统：提供 /whatslink help、test、config 三条辅助命令。

================================================================================
                              配  置  项
================================================================================
所有配置项通过 AstrBot 插件配置页面管理，位于 plugin_settings.astrbot_plugin_whatslinkInfo：

  merge_forward   (boolean, 默认 false)  是否使用合并转发模式（QQ/OneBot）
  no_wake_word    (boolean, 默认 false)  是否免唤醒词触发（true=任意消息触发）
  timeout         (integer, 默认 10)     API 请求超时时间（秒）
  show_screenshots(boolean, 默认 true)   是否在结果中展示截图
  blur_screenshots(boolean, 默认 false)  是否对截图进行模糊处理
  blur_intensity  (integer, 1-9, 默认 3) 截图模糊强度等级

================================================================================
                              命  令  文  档
================================================================================
1. /whatslink help
   • 使用场景：查看插件功能说明和配置项文档
   • 参数：无
   • 示例：/whatslink help

2. /whatslink test <magnet_link>
   • 使用场景：手动测试某个磁力链接的解析结果
   • 参数：magnet_link - 完整的磁力链接 URL
   • 示例：/whatslink test magnet:?xt=urn:btih:ABCDEF1234567890

3. /whatslink config
   • 使用场景：查看当前插件的配置值
   • 参数：无
   • 示例：/whatslink config

================================================================================
                              特  殊  逻  辑
================================================================================
• 当 show_screenshots=true 且 merge_forward=false 时：
  多张截图将按垂直方向拼接成一张图片后发送，拼接时保持原始比例。

• 当 blur_screenshots=true 时：
  截图会先经过高斯模糊（强度由 blur_intensity 控制），再拼接或发送。

• 当 no_wake_word=false 时：
  仅在私聊或命令消息（以 / 开头）中自动识别磁链；群聊需主动使用命令。

================================================================================
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
import time
from typing import List, Optional, Tuple

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Node, Nodes

# ---------------------------------------------------------------------------
# 尝试导入 Pillow；若不可用则禁用截图处理功能
# ---------------------------------------------------------------------------
try:
    from PIL import Image as PILImage
    from PIL import ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow 未安装，截图拼接与模糊功能将不可用。请执行: pip install Pillow")


# ===========================================================================
#  常  量
# ===========================================================================

MAGNET_RE = re.compile(r"(magnet:\?xt=urn:btih:[A-Za-z0-9]+)", re.IGNORECASE)
API_URL = "https://whatslink.info/api/v1/link"

# 插件配置 key（在 plugin_settings 下的键名）
PLUGIN_CONFIG_KEY = "astrbot_plugin_whatslinkInfo"

# 默认配置值
DEFAULT_CONFIG = {
    "merge_forward": False,
    "no_wake_word": False,
    "timeout": 10,
    "show_screenshots": True,
    "blur_screenshots": False,
    "blur_intensity": 3,
}

# API 调用最小间隔（秒），防止触发 whatslink.info 风控
API_COOLDOWN_SEC = 3.0

# 命令前缀
CMD_PREFIX = "/whatslink"


# ===========================================================================
#  工  具  函  数
# ===========================================================================

def _human_readable_size(num) -> str:
    """将字节数格式化为人类可读的字符串（中文单位）。

    参数:
        num: 字节数（int/float/str），可能为 None。

    返回:
        格式化后的字符串，如 "1.50GB"、"512.00MB" 或 "未知"。
    """
    if num is None:
        return "未知"
    try:
        num = int(num)
    except (ValueError, TypeError):
        return str(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"


def _make_image_from_file(file_path: str) -> Image:
    """安全地从本地文件路径创建 AstrBot Image 消息组件。

    尝试多种 AstrBot API 形式以确保兼容性：
    1. Image.fromFile(path)    — 首选（v3.4+ 推荐）
    2. Image(file=path)         — 备选构造器

    参数:
        file_path: 本地图片文件绝对路径。

    返回:
        AstrBot Image 消息组件实例。
    """
    # 优先使用 fromFile 静态方法
    if hasattr(Image, "fromFile"):
        return Image.fromFile(file_path)
    # 回退：直接使用构造器
    try:
        return Image(file=file_path)
    except TypeError:
        # 最终回退：尝试 fromURL（某些平台支持 file:// 协议）
        return Image.fromURL(f"file:///{file_path.replace(chr(92), '/')}")


def _clamp_blur_intensity(value) -> int:
    """将模糊强度限制在 1-9 范围内。

    参数:
        value: 用户配置的模糊强度值。

    返回:
        钳制后的整数值 (1-9)。
    """
    try:
        v = int(value)
    except (ValueError, TypeError):
        return 3
    return max(1, min(9, v))


# ===========================================================================
#  插  件  主  类
# ===========================================================================

@register("astrbot_plugin_whatslinkInfo", "Zhalslar", "磁链解析插件（whatslink.info）v2.0.0", "2.0.0")
class WhatslinkPlugin(Star):
    """whatslink.info 磁力链接解析插件。

    自动识别聊天中的磁力链接，调用 whatslink.info API 获取资源预览信息，
    支持截图拼接、模糊处理、合并转发以及命令交互。
    """

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        # 频率控制：记录上一次 API 调用时间戳（Unix 秒）与异步锁
        self._last_api_call_time: float = 0.0
        self._api_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    #  初始化 / 销毁
    # ------------------------------------------------------------------

    async def initialize(self):
        """插件异步初始化。"""
        logger.info("whatslinkInfo 插件初始化完成")

    async def terminate(self):
        """插件被卸载/停用时调用。"""
        logger.info("whatslinkInfo 插件已终止")

    # ------------------------------------------------------------------
    #  配  置  读  取
    # ------------------------------------------------------------------

    def _get_config(self, event: AstrMessageEvent) -> dict:
        """从 AstrBot 全局配置中读取本插件的配置，缺失项使用默认值。

        参数:
            event: AstrBot 消息事件，用于获取 unified_msg_origin。

        返回:
            合并默认值后的配置字典。
        """
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
        except Exception:
            cfg = {}
        plugin_cfg = cfg.get("plugin_settings", {}).get(PLUGIN_CONFIG_KEY, {})
        # 合并默认值
        merged = dict(DEFAULT_CONFIG)
        for key in DEFAULT_CONFIG:
            if key in plugin_cfg:
                merged[key] = plugin_cfg[key]
        # 类型矫正
        merged["merge_forward"] = bool(merged["merge_forward"])
        merged["no_wake_word"] = bool(merged["no_wake_word"])
        merged["timeout"] = int(merged["timeout"]) if merged["timeout"] else 10
        merged["show_screenshots"] = bool(merged["show_screenshots"])
        merged["blur_screenshots"] = bool(merged["blur_screenshots"])
        merged["blur_intensity"] = _clamp_blur_intensity(merged.get("blur_intensity", 3))
        return merged

    # ------------------------------------------------------------------
    #  唤  醒  词  检  测
    # ------------------------------------------------------------------

    def _is_bot_addressed(self, event: AstrMessageEvent) -> bool:
        """判断机器人是否被明确呼叫（用于 no_wake_word=false 时的过滤）。

        检查逻辑：
        1. 消息以 '/' 开头 → 视为命令消息，已呼叫。
        2. 私聊消息 → 视为已呼叫。
        3. 群聊中消息链包含 At 组件 → 视为已呼叫。
        4. 其他情况 → 未呼叫。

        参数:
            event: AstrBot 消息事件。

        返回:
            True 表示已呼叫，False 表示未呼叫。
        """
        text = event.get_message_str().strip()

        # 命令消息
        if text.startswith("/"):
            return True

        # 私聊检测
        umo = event.unified_msg_origin
        if hasattr(umo, "is_private") and callable(getattr(umo, "is_private", None)):
            try:
                if umo.is_private():
                    return True
            except Exception:
                pass
        if hasattr(umo, "message_type") and str(getattr(umo, "message_type", "")).lower() == "private":
            return True

        # 群聊 @检测
        try:
            message_chain = event.get_message()
            for comp in message_chain:
                if type(comp).__name__ == "At":
                    return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    #  API  调  用
    # ------------------------------------------------------------------

    async def _call_api(self, url: str, timeout_sec: int = 10) -> Optional[dict]:
        """调用 whatslink.info API 获取磁链解析数据。

        内置频率控制：使用异步锁确保串行调用，并强制最小调用间隔
        API_COOLDOWN_SEC 秒，防止触发风控。

        参数:
            url: 磁力链接 URL。
            timeout_sec: 请求超时秒数。

        返回:
            成功返回 API JSON 字典；失败返回 None。
        """
        # ---- 频率控制：确保两次 API 调用间隔 ≥ API_COOLDOWN_SEC 秒 ----
        async with self._api_lock:
            now = time.time()
            elapsed = now - self._last_api_call_time
            if elapsed < API_COOLDOWN_SEC:
                wait_sec = API_COOLDOWN_SEC - elapsed
                logger.debug(f"API 频率限制：距上次调用仅 {elapsed:.1f}s，等待 {wait_sec:.1f}s...")
                await asyncio.sleep(wait_sec)
            # 在实际发起请求前更新时间戳，避免并发窗口内的重复调用
            self._last_api_call_time = time.time()

        # ---- 发起 API 请求 ----
        params = {"url": url}
        timeout = aiohttp.ClientTimeout(total=timeout_sec if timeout_sec > 0 else None)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(API_URL, params=params, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.warning(f"whatslink.info API 返回非 200 状态码: {resp.status}，URL={url[:80]}...")
                        return None
                    data = await resp.json()
                    logger.debug(f"API 响应: {str(data)[:200]}...")
                    return data
        except asyncio.TimeoutError:
            logger.warning(f"whatslink.info API 请求超时 ({timeout_sec}s): {url[:80]}...")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"whatslink.info 网络请求异常: {e}")
            return None
        except Exception as e:
            logger.error(f"whatslink.info API 调用未知错误: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    #  截  图  处  理
    # ------------------------------------------------------------------

    async def _download_screenshots(
        self,
        urls: List[str],
        blur: bool = False,
        blur_intensity: int = 3,
    ) -> Tuple[List[io.BytesIO], List[str]]:
        """下载截图并可选进行模糊处理。

        参数:
            urls: 截图 URL 列表。
            blur: 是否模糊处理。
            blur_intensity: 模糊强度 (1-9)。

        返回:
            (成功下载的 BytesIO 列表, 对应临时文件路径列表)。
            调用方需在发送后清理临时文件。
        """
        images: List[io.BytesIO] = []
        temp_paths: List[str] = []

        if not _PIL_AVAILABLE and blur:
            logger.warning("Pillow 不可用，无法进行截图模糊处理")
            blur = False

        async with aiohttp.ClientSession(trust_env=True) as session:
            for idx, url in enumerate(urls):
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            logger.warning(f"下载截图失败 (HTTP {resp.status}): {url[:80]}...")
                            continue
                        raw_data = await resp.read()
                        logger.debug(f"截图 [{idx}] 下载成功: {len(raw_data)} bytes")

                        if blur and _PIL_AVAILABLE:
                            # 打开 → 模糊 → 输出为 PNG 字节
                            pil_img = PILImage.open(io.BytesIO(raw_data))
                            if pil_img.mode != "RGB":
                                pil_img = pil_img.convert("RGB")
                            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=blur_intensity))
                            buf = io.BytesIO()
                            pil_img.save(buf, format="PNG")
                            buf.seek(0)
                            images.append(buf)
                        else:
                            images.append(io.BytesIO(raw_data))

                except asyncio.TimeoutError:
                    logger.warning(f"下载截图超时: {url[:80]}...")
                except Exception as e:
                    logger.warning(f"下载截图异常 [{idx}]: {e}")

        return images, temp_paths

    def _concatenate_vertical(self, image_buffers: List[io.BytesIO]) -> Optional[io.BytesIO]:
        """将多张图片垂直拼接为一张 PNG 图片。

        拼接规则：
        - 计算所有图片的最大宽度作为画布宽度。
        - 计算所有图片高度之和作为画布高度。
        - 每张图片水平居中放置。
        - 保持各图片原始宽高比，不进行缩放。
        - 以白色背景填充空白区域。

        参数:
            image_buffers: BytesIO 列表，每个元素为一张图片的字节数据。

        返回:
            拼接后的 PNG 图片 BytesIO；图片列表为空或处理失败时返回 None。
        """
        if not _PIL_AVAILABLE:
            logger.warning("Pillow 不可用，无法进行截图拼接")
            return None
        if not image_buffers:
            return None

        pil_images = []
        for buf in image_buffers:
            try:
                buf.seek(0)
                img = PILImage.open(buf)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                pil_images.append(img)
            except Exception as e:
                logger.warning(f"无法打开截图进行拼接: {e}")
                continue

        if not pil_images:
            return None

        # 单张图片直接返回，无需拼接
        if len(pil_images) == 1:
            output = io.BytesIO()
            pil_images[0].save(output, format="PNG", optimize=True)
            output.seek(0)
            return output

        # 计算画布尺寸
        max_width = max(img.width for img in pil_images)
        total_height = sum(img.height for img in pil_images)

        # 创建白色背景画布
        canvas = PILImage.new("RGB", (max_width, total_height), (255, 255, 255))

        # 逐张粘贴
        y_offset = 0
        for img in pil_images:
            x_offset = (max_width - img.width) // 2  # 水平居中
            canvas.paste(img, (x_offset, y_offset))
            y_offset += img.height

        # 输出为 PNG
        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
        output.seek(0)
        logger.debug(f"截图拼接完成: {len(pil_images)} 张 → {max_width}x{total_height}")
        return output

    async def _process_screenshots(
        self,
        screenshot_urls: List[str],
        merge_forward: bool,
        blur: bool,
        blur_intensity: int,
    ) -> Tuple[Optional[io.BytesIO], List[io.BytesIO], List[str]]:
        """处理截图的完整流程：下载 → 可选模糊 → 可选拼接。

        参数:
            screenshot_urls: 原始截图 URL 列表。
            merge_forward: 是否合并转发模式。
            blur: 是否模糊。
            blur_intensity: 模糊强度。

        返回:
            (拼接图 BytesIO 或 None, 单图 BytesIO 列表, 临时文件路径列表)
            - 非合并转发模式：返回拼接图（单张时直接返回原图）。
            - 合并转发模式：返回单图列表 + 拼接图均为有效值。
        """
        temp_paths: List[str] = []

        # 下载并可选模糊处理
        images, _ = await self._download_screenshots(screenshot_urls, blur=blur, blur_intensity=blur_intensity)

        if not images:
            return None, [], temp_paths

        if merge_forward:
            # 合并转发模式：返回原始单图列表（不拼接），再提供一个拼接图备用
            concatenated = self._concatenate_vertical(images)
            # 重新 seek 每个 buffer 到开头，以便后续写入文件
            for img in images:
                img.seek(0)
            return concatenated, images, temp_paths
        else:
            # 非合并转发模式：拼接为一张图
            concatenated = self._concatenate_vertical(images)
            return concatenated, [], temp_paths

    def _save_image_to_temp(self, image_buffer: io.BytesIO) -> Optional[str]:
        """将 BytesIO 中的图片保存为临时 PNG 文件。

        参数:
            image_buffer: 图片字节数据。

        返回:
            临时文件路径；失败返回 None。
        """
        try:
            image_buffer.seek(0)
            fd, path = tempfile.mkstemp(suffix=".png", prefix="whatslink_")
            with os.fdopen(fd, "wb") as f:
                f.write(image_buffer.read())
            return path
        except Exception as e:
            logger.error(f"保存临时图片失败: {e}")
            return None

    def _cleanup_temp_files(self, paths: List[str]):
        """清理临时图片文件。

        参数:
            paths: 临时文件路径列表。
        """
        for p in paths:
            try:
                if p and os.path.exists(p):
                    os.unlink(p)
            except Exception as e:
                logger.debug(f"清理临时文件失败 {p}: {e}")

    # ------------------------------------------------------------------
    #  消  息  构  建
    # ------------------------------------------------------------------

    def _build_result_message(
        self,
        event: AstrMessageEvent,
        api_data: dict,
        cfg: dict,
        concatenated_image: Optional[io.BytesIO],
        single_images: List[io.BytesIO],
    ) -> Tuple[MessageEventResult, List[str]]:
        """根据 API 数据和配置构建最终的回复消息。

        参数:
            event: 消息事件。
            api_data: whatslink.info API 返回的 JSON 数据。
            cfg: 当前插件配置字典。
            concatenated_image: 拼接后的截图（非合并转发模式使用）。
            single_images: 单张截图列表（合并转发模式使用）。

        返回:
            (MessageEventResult, 临时文件路径列表)。
        """
        temp_paths: List[str] = []
        merge_forward = cfg["merge_forward"]
        show_screenshots = cfg["show_screenshots"]

        # 解析 API 响应字段
        name = api_data.get("name", "未知名称")
        size = api_data.get("size")
        count = api_data.get("count")
        file_type = api_data.get("file_type", api_data.get("type", ""))

        # 构建文本头部
        header = (
            f"📦 名称: {name}\n"
            f"📄 文件数量: {count if count is not None else '未知'}\n"
            f"📏 总大小: {size if size is not None else '未知'} ({_human_readable_size(size)})\n"
        )
        if file_type:
            header += f"📂 类型: {file_type}\n"
        header = header.rstrip("\n")

        mer = MessageEventResult()

        if merge_forward and event.get_platform_name() in ("aiocqhttp", "qq", "qq_official", "onebot"):
            # ---- 合并转发模式 ----
            content: List = [Plain(header)]

            if show_screenshots:
                if concatenated_image:
                    # 有拼接图时使用单张拼接图
                    temp_path = self._save_image_to_temp(concatenated_image)
                    if temp_path:
                        temp_paths.append(temp_path)
                        content.append(_make_image_from_file(temp_path))
                elif single_images:
                    # 逐一添加截图
                    for img_buf in single_images:
                        temp_path = self._save_image_to_temp(img_buf)
                        if temp_path:
                            temp_paths.append(temp_path)
                            content.append(_make_image_from_file(temp_path))

            node = Node(
                content=content,
                name=event.get_sender_name() or "磁链解析",
                uin=str(event.get_sender_id() or ""),
            )
            nodes = Nodes(nodes=[node])
            mer.chain = [nodes]

        else:
            # ---- 普通模式 ----
            mer = mer.message(header)

            if show_screenshots and concatenated_image:
                temp_path = self._save_image_to_temp(concatenated_image)
                if temp_path:
                    temp_paths.append(temp_path)
                    mer.chain.append(_make_image_from_file(temp_path))

        return mer, temp_paths

    # ------------------------------------------------------------------
    #  命  令  处  理
    # ------------------------------------------------------------------

    def _build_help_text(self, cfg: dict) -> str:
        """构建帮助信息文本。

        参数:
            cfg: 当前配置字典。

        返回:
            帮助信息字符串。
        """
        blur_note = " (Pillow 未安装，此功能不可用)" if not _PIL_AVAILABLE else ""
        return (
            "━━━ whatslinkInfo 磁链解析插件 ━━━\n"
            "\n"
            "【自动功能】\n"
            "  发送包含磁力链接的消息即可自动识别并解析。\n"
            "\n"
            "【命令列表】\n"
            f"  {CMD_PREFIX} help         查看此帮助\n"
            f"  {CMD_PREFIX} test  <链接> 测试磁链解析\n"
            f"  {CMD_PREFIX} config       查看当前配置\n"
            "\n"
            "【当前配置】\n"
            f"  merge_forward   : {cfg['merge_forward']}\n"
            f"  no_wake_word    : {cfg['no_wake_word']}\n"
            f"  timeout         : {cfg['timeout']} 秒\n"
            f"  show_screenshots: {cfg['show_screenshots']}\n"
            f"  blur_screenshots: {cfg['blur_screenshots']}{blur_note}\n"
            f"  blur_intensity  : {cfg['blur_intensity']} (1-9)\n"
            "\n"
            "【配置方法】在 AstrBot 插件配置页面修改上述参数。\n"
            "  配置路径: plugin_settings → astrbot_plugin_whatslinkInfo"
        )

    def _build_config_text(self, cfg: dict) -> str:
        """构建当前配置信息文本。

        参数:
            cfg: 当前配置字典。

        返回:
            配置信息字符串。
        """
        blur_note = " (Pillow 未安装)" if not _PIL_AVAILABLE else ""
        return (
            "⚙️ whatslinkInfo 当前配置\n"
            "\n"
            f"  merge_forward    : {cfg['merge_forward']}\n"
            f"  no_wake_word     : {cfg['no_wake_word']}\n"
            f"  timeout          : {cfg['timeout']} 秒\n"
            f"  show_screenshots : {cfg['show_screenshots']}\n"
            f"  blur_screenshots : {cfg['blur_screenshots']}{blur_note}\n"
            f"  blur_intensity   : {cfg['blur_intensity']} (范围 1-9)\n"
            "\n"
            "可通过 AstrBot 插件配置页面修改以上参数。"
        )

    async def _handle_command(self, event: AstrMessageEvent, cfg: dict):
        """处理 /whatslink 开头的命令消息。

        参数:
            event: 消息事件。
            cfg: 当前插件配置。
        """
        text = event.get_message_str().strip()
        # 移除命令前缀，支持 "/whatslink" 和 "whatslink" 开头
        if text.startswith(CMD_PREFIX):
            args_text = text[len(CMD_PREFIX):].strip()
        elif text.lower().startswith("whatslink"):
            args_text = text[9:].strip()
        else:
            args_text = text

        parts = args_text.split(maxsplit=1)
        sub_cmd = parts[0].lower() if parts else ""

        if sub_cmd in ("help", "帮助", "-h", "--help"):
            # ---- help 命令 ----
            help_text = self._build_help_text(cfg)
            try:
                yield event.plain_result(help_text)
            except Exception as e:
                logger.error(f"发送帮助信息失败: {e}")

        elif sub_cmd in ("config", "配置", "-c"):
            # ---- config 命令 ----
            config_text = self._build_config_text(cfg)
            try:
                yield event.plain_result(config_text)
            except Exception as e:
                logger.error(f"发送配置信息失败: {e}")

        elif sub_cmd in ("test", "测试", "-t"):
            # ---- test 命令 ----
            if len(parts) < 2 or not parts[1].strip():
                yield event.plain_result(
                    "⚠️ 请提供磁力链接。用法: /whatslink test <magnet_link>"
                )
                return

            magnet = parts[1].strip()
            # 校验是否是磁力链接格式
            if not MAGNET_RE.match(magnet):
                yield event.plain_result(
                    f"⚠️ 无效的磁力链接格式。\n"
                    f"应为 magnet:?xt=urn:btih:... 开头\n"
                    f"收到: {magnet[:80]}"
                )
                return

            # 执行解析
            yield event.plain_result("🔍 正在解析磁链，请稍候...")

            result_event = await self._parse_single_magnet(event, magnet, cfg)
            if result_event:
                try:
                    await self.context.send_message(event.unified_msg_origin, result_event)
                except Exception as e:
                    logger.error(f"发送 test 解析结果失败: {e}")

        else:
            # 未知子命令
            yield event.plain_result(
                f"❓ 未知命令: {sub_cmd}\n"
                f"可用命令: help, test, config\n"
                f"示例: {CMD_PREFIX} help"
            )

    # ------------------------------------------------------------------
    #  单  条  磁  链  解  析
    # ------------------------------------------------------------------

    async def _parse_single_magnet(
        self,
        event: AstrMessageEvent,
        magnet: str,
        cfg: dict,
    ) -> Optional[MessageEventResult]:
        """解析单条磁力链接，构建结果消息。

        参数:
            event: 消息事件。
            magnet: 磁力链接 URL。
            cfg: 插件配置字典。

        返回:
            MessageEventResult 或 None（解析失败时）。
        """
        timeout_sec = cfg["timeout"]
        show_screenshots = cfg["show_screenshots"]
        blur = cfg["blur_screenshots"]
        blur_intensity = cfg["blur_intensity"]
        merge_forward = cfg["merge_forward"]

        # 调用 API
        api_data = await self._call_api(magnet, timeout_sec=timeout_sec)
        if not api_data:
            mer = MessageEventResult().message(f"❌ 解析失败: API 请求超时或网络错误\n{magnet[:80]}...")
            return mer

        # 检查 API 错误
        err = api_data.get("error") or ""
        if err:
            mer = MessageEventResult().message(f"❌ 解析失败: {err}")
            return mer

        # 截图处理
        screenshots = api_data.get("screenshots", []) or []
        shot_urls: List[str] = []
        if show_screenshots and isinstance(screenshots, list):
            for s in screenshots:
                url = s.get("screenshot") if isinstance(s, dict) else str(s)
                if url:
                    shot_urls.append(url)

        concatenated = None
        single_images = []
        temp_paths = []

        if shot_urls:
            concatenated, single_images, temp_paths = await self._process_screenshots(
                shot_urls,
                merge_forward=merge_forward,
                blur=blur,
                blur_intensity=blur_intensity,
            )

        # 构建消息
        mer, new_temp_paths = self._build_result_message(
            event, api_data, cfg, concatenated, single_images
        )
        temp_paths.extend(new_temp_paths)

        # 将临时路径附加到 mer 上以便后续清理（通过扩展属性）
        mer._temp_paths = temp_paths  # type: ignore[attr-defined]

        return mer

    # ------------------------------------------------------------------
    #  消  息  监  听
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，自动识别磁力链接或处理命令。

        处理流程：
        1. 检查是否为 /whatslink 命令 → 交给 _handle_command 处理。
        2. 提取消息中的磁力链接。
        3. 根据 no_wake_word 配置判断是否响应。
        4. 依次解析每条磁链并发送结果。

        参数:
            event: AstrBot 消息事件。
        """
        text = event.get_message_str() or ""
        if not text.strip():
            return

        # 读取配置
        cfg = self._get_config(event)
        no_wake_word = cfg["no_wake_word"]

        # ----- 命令处理 -----
        if text.strip().lower().startswith(CMD_PREFIX) or text.strip().lower().startswith("whatslink "):
            async for result in self._handle_command(event, cfg):
                yield result  # 将命令结果传播给框架
            return

        # ----- 磁链自动识别 -----
        magnets = MAGNET_RE.findall(text)
        if not magnets:
            return

        # 唤醒词检查
        if not no_wake_word and not self._is_bot_addressed(event):
            logger.debug(f"no_wake_word=false 且未呼叫机器人，跳过磁链处理")
            return

        # 一次仅解析第一条磁链，避免 API 频率过高触发风控
        if len(magnets) > 1:
            logger.info(f"检测到 {len(magnets)} 条磁力链接，仅解析第一条: {magnets[0][:80]}...")
        else:
            logger.info(f"检测到 1 条磁力链接，开始解析: {magnets[0][:80]}...")

        # 发送"解析中"提示
        try:
            yield event.plain_result("🔍 解析磁链中...")
        except Exception:
            pass

        all_temp_paths: List[str] = []

        try:
            magnet = magnets[0]
            logger.debug(f"解析磁链: {magnet[:80]}...")

            result_event = await self._parse_single_magnet(event, magnet, cfg)
            if result_event:
                # 收集临时文件路径
                if hasattr(result_event, "_temp_paths"):
                    all_temp_paths.extend(result_event._temp_paths)  # type: ignore[attr-defined]
                try:
                    await self.context.send_message(event.unified_msg_origin, result_event)
                except Exception as e:
                    logger.error(f"发送解析结果失败: {e}")
        finally:
            # 清理临时文件
            self._cleanup_temp_files(all_temp_paths)