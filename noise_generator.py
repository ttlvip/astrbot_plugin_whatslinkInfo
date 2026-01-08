"""
动态随机噪声生成器
用于规避QQ平台的图像内容检测
提供多种噪声类型和智能组合策略
Contributor: acacia
"""

import random
import math
import io
from enum import Enum
from typing import List, Tuple, Dict, Optional

from astrbot.api import logger

try:
    from PIL import Image as PImage
    from PIL import ImageDraw, ImageEnhance, ImageFilter
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


class NoiseType(Enum):
    """噪声类型枚举"""
    COLOR_BAR = "color_bar"           # 彩色条纹
    PIXEL_NOISE = "pixel_noise"       # 像素噪声
    GRADIENT_OVERLAY = "gradient"     # 渐变叠加
    GEOMETRIC_PATTERN = "geometric"   # 几何图案
    TEXT_OVERLAY = "text"             # 文字水印
    BLUR_PATCHES = "blur_patches"     # 局部模糊
    BRIGHTNESS_SPOT = "brightness"    # 亮度斑点
    COMPRESSION_ARTIFACT = "artifact" # 压缩噪点
    NOISE_WAVE = "noise_wave"         # 波纹噪声


class NoiseParams:
    """噪声参数配置"""
    def __init__(self):
        self.intensity = random.uniform(0.1, 0.8)      # 噪声强度
        self.coverage = random.uniform(0.05, 0.3)      # 覆盖范围
        self.color_scheme = random.choice(['mono', 'rgb', 'gradient'])  # 配色方案
        self.position_strategy = random.choice(['random', 'distributed', 'focused'])  # 位置策略
        self.blend_mode = random.choice(['normal', 'multiply', 'overlay', 'screen'])  # 混合模式

        # 位置参数
        self.regions = random.randint(1, 5)            # 噪声区域数
        self.min_size = random.randint(20, 100)        # 最小尺寸
        self.max_size = random.randint(100, 300)       # 最大尺寸

        # 动画参数（用于生成序列）
        self.frame_count = random.randint(3, 8)        # 帧数
        self.transition = random.choice(['fade', 'slide', 'morph'])  # 过渡效果

        # 种子，用于可重现的随机性
        self.seed = random.randint(0, 2**32 - 1)


class NoiseGenerator:
    """噪声生成器基类"""
    def __init__(self, params: Optional[NoiseParams] = None):
        self.params = params or NoiseParams()
        # 使用固定种子保证同一生成器的行为一致
        random.seed(self.params.seed)

    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        """生成噪声，返回带噪声的图像"""
        raise NotImplementedError

    def _get_random_color(self) -> Tuple[int, int, int]:
        """获取随机颜色"""
        if self.params.color_scheme == 'mono':
            gray = random.randint(0, 100)
            return (gray, gray, gray)
        elif self.params.color_scheme == 'rgb':
            return (
                random.randint(0, 150),
                random.randint(0, 150),
                random.randint(0, 150)
            )
        else:  # gradient
            base_hue = random.randint(0, 360)
            return self._hsv_to_rgb(base_hue, random.uniform(0.2, 0.8), random.uniform(0.2, 0.6))

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> Tuple[int, int, int]:
        """HSV转RGB"""
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (
            int((r + m) * 255),
            int((g + m) * 255),
            int((b + m) * 255)
        )


class ColorBarNoise(NoiseGenerator):
    """彩色条纹噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()

        # 生成多个条纹
        for i in range(random.randint(3, 8)):
            # 随机位置和大小
            if self.params.position_strategy == 'random':
                x = random.randint(0, w - 50)
                y = random.randint(0, h - 50)
                bar_w = random.randint(20, min(150, w - x))
                bar_h = random.randint(10, min(80, h - y))
                angle = random.randint(-30, 30)
            else:  # distributed
                angle = 90 if random.random() < 0.5 else 0
                if angle == 90:  # 垂直条纹
                    x = int((i + 1) * w / (self.params.regions + 1))
                    y = 0
                    bar_w = random.randint(10, 30)
                    bar_h = h
                else:  # 水平条纹
                    x = 0
                    y = int((i + 1) * h / (self.params.regions + 1))
                    bar_w = w
                    bar_h = random.randint(10, 30)

            # 创建条纹
            bar = PImage.new("RGBA", (bar_w, bar_h), self._get_random_color() + (int(self.params.intensity * 255),))

            # 旋转条纹
            if angle != 0:
                bar = bar.rotate(angle, expand=True)

            # 叠加到结果图
            result.paste(bar, (x, y), bar)

        return result


class PixelNoise(NoiseGenerator):
    """像素级噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()
        pixels = result.load()

        # 计算噪声像素数量
        noise_count = int(w * h * self.params.coverage)

        for _ in range(noise_count):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)

            if random.random() < self.params.intensity:
                # 获取原像素
                r, g, b = pixels[x, y]

                # 添加噪声
                noise_type = random.choice(['offset', 'invert', 'colorize'])
                if noise_type == 'offset':
                    pixels[x, y] = (
                        min(255, max(0, r + random.randint(-50, 50))),
                        min(255, max(0, g + random.randint(-50, 50))),
                        min(255, max(0, b + random.randint(-50, 50)))
                    )
                elif noise_type == 'invert':
                    factor = random.uniform(0.3, 0.7)
                    pixels[x, y] = (
                        int(r * (1 - factor) + (255 - r) * factor),
                        int(g * (1 - factor) + (255 - g) * factor),
                        int(b * (1 - factor) + (255 - b) * factor)
                    )
                else:  # colorize
                    color = self._get_random_color()
                    pixels[x, y] = (
                        int(r * 0.5 + color[0] * 0.5),
                        int(g * 0.5 + color[1] * 0.5),
                        int(b * 0.5 + color[2] * 0.5)
                    )

        return result


class GradientNoise(NoiseGenerator):
    """渐变叠加噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()

        # 创建渐变蒙版
        overlay = PImage.new("RGBA", (w, h), (255, 255, 255, 0))
        pixels = overlay.load()

        # 选择渐变方向
        direction = random.choice(['horizontal', 'vertical', 'radial', 'diagonal', 'circular'])

        if direction == 'horizontal':
            for x in range(w):
                intensity = int(self.params.intensity * 255 * random.uniform(0.3, 1.0) * (x / w))
                color = self._get_random_color()
                for y in range(h):
                    pixels[x, y] = color + (intensity,)

        elif direction == 'vertical':
            for y in range(h):
                intensity = int(self.params.intensity * 255 * random.uniform(0.3, 1.0) * (y / h))
                color = self._get_random_color()
                for x in range(w):
                    pixels[x, y] = color + (intensity,)

        elif direction == 'radial':
            center_x, center_y = w // 2, h // 2
            max_dist = math.sqrt(center_x**2 + center_y**2)

            for x in range(w):
                for y in range(h):
                    dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                    intensity = int(self.params.intensity * 255 * random.uniform(0.3, 1.0) * (1 - dist / max_dist))
                    color = self._get_random_color()
                    pixels[x, y] = color + (max(0, min(255, intensity)),)

        elif direction == 'circular':
            center_x = random.randint(w // 4, 3 * w // 4)
            center_y = random.randint(h // 4, 3 * h // 4)
            radius = random.randint(min(w, h) // 4, min(w, h) // 2)

            for x in range(w):
                for y in range(h):
                    dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                    if dist <= radius:
                        intensity = int(self.params.intensity * 255 * random.uniform(0.3, 1.0) * (1 - dist / radius))
                        color = self._get_random_color()
                        pixels[x, y] = color + (intensity,)

        # 混合模式
        result = PImage.alpha_composite(result.convert("RGBA"), overlay)
        return result.convert("RGB")


class GeometricPatternNoise(NoiseGenerator):
    """几何图案噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()

        # 创建透明图层
        overlay = PImage.new("RGBA", (w, h), (255, 255, 255, 0))

        # 选择图案类型
        pattern = random.choice(['circles', 'triangles', 'rectangles', 'lines', 'dots'])

        for _ in range(random.randint(5, 15)):
            if pattern == 'circles':
                x = random.randint(20, w - 20)
                y = random.randint(20, h - 20)
                radius = random.randint(10, 50)
                color = self._get_random_color() + (int(self.params.intensity * 128),)

                # 绘制圆形
                for px in range(max(0, x - radius), min(w, x + radius)):
                    for py in range(max(0, y - radius), min(h, y + radius)):
                        if (px - x)**2 + (py - y)**2 <= radius**2:
                            overlay.putpixel((px, py), color)

            elif pattern == 'triangles':
                points = []
                for _ in range(3):
                    points.append((random.randint(0, w), random.randint(0, h)))
                color = self._get_random_color() + (int(self.params.intensity * 128),)
                # 简单填充三角形中心
                cx = sum(p[0] for p in points) // 3
                cy = sum(p[1] for p in points) // 3
                for px in range(max(0, cx - 20), min(w, cx + 20)):
                    for py in range(max(0, cy - 20), min(h, cy + 20)):
                        overlay.putpixel((px, py), color)

            elif pattern == 'rectangles':
                x = random.randint(0, w - 50)
                y = random.randint(0, h - 50)
                width = random.randint(20, 100)
                height = random.randint(20, 100)
                color = self._get_random_color() + (int(self.params.intensity * 128),)

                for px in range(x, min(w, x + width)):
                    for py in range(y, min(h, y + height)):
                        overlay.putpixel((px, py), color)

            elif pattern == 'lines':
                x1 = random.randint(0, w)
                y1 = random.randint(0, h)
                x2 = random.randint(0, w)
                y2 = random.randint(0, h)
                color = self._get_random_color() + (int(self.params.intensity * 128),)

                # 绘制线条
                steps = max(abs(x2 - x1), abs(y2 - y1))
                for i in range(steps):
                    t = i / steps if steps > 0 else 0
                    px = int(x1 + t * (x2 - x1))
                    py = int(y1 + t * (y2 - y1))
                    if 0 <= px < w and 0 <= py < h:
                        for dx in range(-1, 2):
                            for dy in range(-1, 2):
                                if 0 <= px + dx < w and 0 <= py + dy < h:
                                    overlay.putpixel((px + dx, py + dy), color)

            elif pattern == 'dots':
                for _ in range(random.randint(20, 50)):
                    x = random.randint(0, w - 1)
                    y = random.randint(0, h - 1)
                    color = self._get_random_color() + (int(self.params.intensity * 255),)
                    overlay.putpixel((x, y), color)

        # 混合到结果
        result = PImage.alpha_composite(result.convert("RGBA"), overlay)
        return result.convert("RGB")


class BlurPatchNoise(NoiseGenerator):
    """局部模糊噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()

        # 选择模糊区域
        for _ in range(random.randint(2, 5)):
            x = random.randint(0, w - 100)
            y = random.randint(0, h - 100)
            size = random.randint(30, min(150, min(w - x, h - y)))

            # 提取区域
            region = result.crop((x, y, x + size, y + size))

            # 应用模糊
            blur_radius = random.uniform(1, 5)
            region = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            # 添加色彩偏移
            if random.random() < 0.5:
                enhancer = ImageEnhance.Color(region)
                region = enhancer.enhance(random.uniform(0.8, 1.2))

            # 贴回原图
            result.paste(region, (x, y))

        return result


class NoiseWaveGenerator(NoiseGenerator):
    """波纹噪声生成器"""
    def generate(self, base_img: PImage.Image, frame_id: int = 0) -> PImage.Image:
        w, h = base_img.size
        result = base_img.copy()

        # 波纹参数
        amplitude = random.randint(5, 20)
        frequency = random.uniform(0.01, 0.05)
        phase = frame_id * 0.5

        # 创建新图像
        new_img = PImage.new("RGB", (w, h), (255, 255, 255))
        pixels = new_img.load()

        # 应用波纹变换
        for y in range(h):
            for x in range(w):
                # 计算波纹偏移
                offset_x = int(amplitude * math.sin(frequency * y + phase))
                offset_y = int(amplitude * math.sin(frequency * x + phase))

                # 获取源像素
                src_x = max(0, min(w - 1, x + offset_x))
                src_y = max(0, min(h - 1, y + offset_y))

                pixels[x, y] = result.getpixel((src_x, src_y))

        return new_img


class NoiseComposer:
    """噪声组合器 - 负责协调多种噪声的生成和组合"""

    def __init__(self):
        self.generators: Dict[NoiseType, type] = {
            NoiseType.COLOR_BAR: ColorBarNoise,
            NoiseType.PIXEL_NOISE: PixelNoise,
            NoiseType.GRADIENT_OVERLAY: GradientNoise,
            NoiseType.GEOMETRIC_PATTERN: GeometricPatternNoise,
            NoiseType.BLUR_PATCHES: BlurPatchNoise,
            NoiseType.NOISE_WAVE: NoiseWaveGenerator,
        }

    def generate_variants(self, base_img_bytes: bytes, count: int = 5, strategy: str = "random") -> List[bytes]:
        """
        生成多个噪声变体

        Args:
            base_img_bytes: 基础图片字节数据
            count: 要生成的变体数量
            strategy: 噪声策略（random, balanced, minimal, aggressive）

        Returns:
            List[bytes]: 变体图片字节数据列表
        """
        if not HAS_PILLOW:
            return []

        try:
            # 加载基础图片
            base_img = PImage.open(io.BytesIO(base_img_bytes))

            variants = []

            for i in range(count):
                # 每个变体使用不同的策略
                noise_strategy = self._select_strategy(i, strategy)
                variant_img = self._apply_strategy(base_img, noise_strategy, frame_id=i)

                # 转换为字节
                try:
                    output = io.BytesIO()
                    variant_img.save(output, format="JPEG", quality=85, optimize=True)
                    variants.append(output.getvalue())
                except Exception as e:
                    logger.warning(f"保存噪声变体失败: {e}")
                finally:
                    output.close()

            return variants

        except Exception as e:
            logger.error(f"生成噪声变体失败: {e}")
            return []

    def _select_strategy(self, variant_id: int, strategy_type: str = "random") -> List[NoiseType]:
        """为每个变体选择噪声策略

        Args:
            variant_id: 变体索引
            strategy_type: 策略类型
                - random: 随机选择
                - balanced: 平衡的噪声组合
                - minimal: 轻微噪声
                - aggressive: 激进噪声
        """
        strategies_map = {
            "minimal": [
                [NoiseType.PIXEL_NOISE],
                [NoiseType.GRADIENT_OVERLAY],
            ],
            "balanced": [
                [NoiseType.COLOR_BAR, NoiseType.PIXEL_NOISE],
                [NoiseType.GRADIENT_OVERLAY, NoiseType.GEOMETRIC_PATTERN],
                [NoiseType.PIXEL_NOISE, NoiseType.BLUR_PATCHES],
                [NoiseType.GRADIENT_OVERLAY, NoiseType.NOISE_WAVE],
            ],
            "aggressive": [
                [NoiseType.COLOR_BAR, NoiseType.PIXEL_NOISE, NoiseType.BLUR_PATCHES],
                [NoiseType.GRADIENT_OVERLAY, NoiseType.GEOMETRIC_PATTERN, NoiseType.NOISE_WAVE],
                [NoiseType.COLOR_BAR, NoiseType.BLUR_PATCHES, NoiseType.NOISE_WAVE],
                [NoiseType.GEOMETRIC_PATTERN, NoiseType.BLUR_PATCHES, NoiseType.PIXEL_NOISE],
            ],
            "random": [
                # 轻度噪声
                [NoiseType.PIXEL_NOISE],
                [NoiseType.GRADIENT_OVERLAY],
                # 中度噪声
                [NoiseType.COLOR_BAR, NoiseType.PIXEL_NOISE],
                [NoiseType.GRADIENT_OVERLAY, NoiseType.GEOMETRIC_PATTERN],
                # 重度噪声
                [NoiseType.COLOR_BAR, NoiseType.PIXEL_NOISE, NoiseType.BLUR_PATCHES],
                [NoiseType.GRADIENT_OVERLAY, NoiseType.GEOMETRIC_PATTERN, NoiseType.NOISE_WAVE],
                # 特殊组合
                [NoiseType.NOISE_WAVE, NoiseType.PIXEL_NOISE],
                [NoiseType.BLUR_PATCHES, NoiseType.GRADIENT_OVERLAY],
            ]
        }

        # 获取对应策略类型的策略列表
        strategies = strategies_map.get(strategy_type, strategies_map["random"])

        # 根据variant_id选择策略，确保多样性
        return strategies[variant_id % len(strategies)]

    def _apply_strategy(self, base_img: PImage.Image, strategy: List[NoiseType], frame_id: int = 0) -> PImage.Image:
        """应用噪声策略"""
        result = base_img.copy()

        # 按顺序应用各种噪声
        for noise_type in strategy:
            generator_class = self.generators.get(noise_type)
            if generator_class:
                generator = generator_class()
                result = generator.generate(result, frame_id)

        return result


# 全局实例
_composer = NoiseComposer()


def generate_noise_variants(image_bytes: bytes, count: int = 5, strategy: str = "random") -> List[bytes]:
    """
    便捷函数：生成噪声变体

    Args:
        image_bytes: 原始图片字节数据
        count: 要生成的变体数量
        strategy: 噪声策略类型

    Returns:
        List[bytes]: 噪声变体列表
    """
    return _composer.generate_variants(image_bytes, count, strategy)


def _parse_edge_sides(edge_sides: str) -> List[str]:
    if not edge_sides:
        return ["top", "bottom"]
    if edge_sides.strip().lower() == "all":
        return ["top", "bottom", "left", "right"]
    parts = [p.strip().lower() for p in edge_sides.replace("|", ",").split(",")]
    sides = [p for p in parts if p in {"top", "bottom", "left", "right"}]
    return sides or ["top", "bottom"]


def _clamp_edge_ratio(value: float) -> float:
    try:
        ratio = float(value)
    except Exception:
        return 0.06
    return max(0.01, min(0.2, ratio))


def _apply_edge_pattern(
    base_img: PImage.Image,
    edge_ratio: float,
    edge_sides: List[str],
    seed: int | None = None,
) -> PImage.Image:
    rng = random.Random(seed) if seed is not None else random
    w, h = base_img.size
    thickness = max(1, int(min(w, h) * edge_ratio * rng.uniform(0.85, 1.15)))
    pads = {
        "top": thickness if "top" in edge_sides else 0,
        "bottom": thickness if "bottom" in edge_sides else 0,
        "left": thickness if "left" in edge_sides else 0,
        "right": thickness if "right" in edge_sides else 0,
    }
    if not any(pads.values()):
        return base_img.copy()

    new_w = w + pads["left"] + pads["right"]
    new_h = h + pads["top"] + pads["bottom"]
    result = PImage.new("RGB", (new_w, new_h), (255, 255, 255))
    result.paste(base_img, (pads["left"], pads["top"]))
    draw = ImageDraw.Draw(result)

    def draw_blocks(side: str, side_len: int):
        block_min = max(1, int(side_len * 0.05))
        block_max = max(block_min + 1, int(side_len * 0.2))
        block_count = max(4, int(side_len / max(1, block_max)))
        block_count = min(block_count, 16)

        for _ in range(block_count):
            block_len = rng.randint(block_min, block_max)
            start = rng.randint(0, max(0, side_len - block_len))
            if side == "top":
                draw.rectangle(
                    [start, 0, start + block_len, pads["top"]],
                    fill=(0, 0, 0),
                )
            elif side == "bottom":
                draw.rectangle(
                    [
                        start,
                        new_h - pads["bottom"],
                        start + block_len,
                        new_h,
                    ],
                    fill=(0, 0, 0),
                )
            elif side == "left":
                draw.rectangle(
                    [0, start, pads["left"], start + block_len],
                    fill=(0, 0, 0),
                )
            elif side == "right":
                draw.rectangle(
                    [
                        new_w - pads["right"],
                        start,
                        new_w,
                        start + block_len,
                    ],
                    fill=(0, 0, 0),
                )

    for side in edge_sides:
        if side in ("top", "bottom"):
            draw_blocks(side, new_w)
        elif side in ("left", "right"):
            draw_blocks(side, new_h)

    return result


def generate_edge_variants(
    image_bytes: bytes,
    count: int = 3,
    edge_ratio: float = 0.06,
    edge_sides: str = "all",
) -> List[bytes]:
    """
    生成边缘黑色图案变体，尽量保持中心清晰

    Args:
        image_bytes: 原始图片字节数据
        count: 变体数量
        edge_ratio: 边缘厚度占短边比例
        edge_sides: 作用边（all/top,bottom,left,right）
    """
    if not HAS_PILLOW:
        return []

    try:
        base_img = PImage.open(io.BytesIO(image_bytes))
    except Exception as e:
        logger.warning(f"加载基础图片失败: {e}")
        return []

    edge_ratio = _clamp_edge_ratio(edge_ratio)
    sides = _parse_edge_sides(edge_sides)
    variants: List[bytes] = []

    for _ in range(count):
        seed = random.randint(0, 2**32 - 1)
        variant_img = _apply_edge_pattern(base_img, edge_ratio, sides, seed=seed)
        output = io.BytesIO()
        try:
            variant_img.save(output, format="JPEG", quality=85, optimize=True)
            variants.append(output.getvalue())
        except Exception as e:
            logger.warning(f"保存边缘变体失败: {e}")
        finally:
            output.close()

    return variants


# 兼容性函数：用于替换原有的简单噪声函数
def add_dynamic_noise(img_bytes: bytes, variant_id: int = 0) -> Optional[bytes]:
    """
    添加动态噪声（单变体）

    Args:
        img_bytes: 原始图片字节数据
        variant_id: 变体ID，用于生成不同的噪声效果

    Returns:
        Optional[bytes]: 添加噪声后的图片字节数据
    """
    variants = generate_noise_variants(img_bytes, count=max(1, variant_id + 1))
    if variant_id < len(variants):
        return variants[variant_id]
    return None
