"""图像验证和处理工具"""

import hashlib
import struct
from PIL import Image
from io import BytesIO
from typing import Tuple


def validate_texture_dimensions(img: Image.Image, is_cape: bool = False) -> bool:
    """
    验证材质尺寸是否合法

    Args:
        img: PIL Image 对象
        is_cape: 是否为披风材质

    Returns:
        bool: 尺寸是否合法
    """
    w, h = img.size
    if is_cape:
        return (w % 64 == 0 and h % 32 == 0) or (w % 22 == 0 and h % 17 == 0)
    else:
        return (w % 64 == 0 and h == w) or (w % 64 == 0 and h * 2 == w)


def compute_texture_hash(image_bytes: bytes) -> str:
    """
    从PNG字节流计算材质Hash（规范算法：基于像素数据）

    Args:
        image_bytes: PNG 图像字节

    Returns:
        str: 材质 hash

    Raises:
        ValueError: 无效的图像数据
    """
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGBA")
        return compute_texture_hash_from_image(img)
    except Exception:
        raise ValueError("Invalid image data")


def compute_texture_hash_from_image(img: Image.Image) -> str:
    """
    实现规范中定义的特殊材质 Hash 算法：基于像素数据的SHA-256
    规范要求计算缓冲区 (width, height, pixels) 的 SHA-256，而非 PNG 文件字节

    Args:
        img: PIL Image 对象（RGBA模式）

    Returns:
        str: 材质 hash（SHA-256 十六进制字符串）
    """
    width, height = img.size
    # 缓冲区大小: w * h * 4 + 8
    buf = bytearray(width * height * 4 + 8)

    # 写入宽和高 (Big-Endian)
    struct.pack_into(">I", buf, 0, width)
    struct.pack_into(">I", buf, 4, height)

    pos = 8
    pixels = img.load()

    for x in range(width):
        for y in range(height):
            r, g, b, a = pixels[x, y]
            # 规范：若 Alpha 为 0，则 RGB 皆处理为 0
            if a == 0:
                r = g = b = 0

            # 写入 ARGB
            buf[pos] = a
            buf[pos + 1] = r
            buf[pos + 2] = g
            buf[pos + 3] = b
            pos += 4

    return hashlib.sha256(buf).hexdigest()


def normalize_png(image_bytes: bytes) -> Tuple[bytes, Image.Image]:
    """
    规范化 PNG 图像，移除多余数据

    Args:
        image_bytes: 原始 PNG 字节

    Returns:
        Tuple[bytes, Image.Image]: (规范化后的字节, PIL Image对象)

    Raises:
        ValueError: 无效的图像数据
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.format != "PNG":
            raise ValueError("Image must be PNG format")

        # 转为 RGBA 并重新保存，去除多余信息
        img = img.convert("RGBA")
        output = BytesIO()
        img.save(output, format="PNG")
        return output.getvalue(), img
    except Exception as e:
        raise ValueError(f"Failed to normalize PNG: {str(e)}")


def extract_skin_head_avatar(image_bytes: bytes, output_size: int = 256) -> bytes:
    """
    从皮肤中截取正脸头像（含帽子层）并输出为方形 PNG。

    支持 64x64、64x32 以及其高清等比尺寸。
    """
    try:
        skin = Image.open(BytesIO(image_bytes)).convert("RGBA")
    except Exception as e:
        raise ValueError(f"Invalid skin image: {str(e)}")

    width, height = skin.size
    if width < 64 or height < 32 or width % 64 != 0:
        raise ValueError("Invalid skin dimensions for avatar extraction")

    scale = width // 64
    if scale <= 0:
        raise ValueError("Invalid skin scale")

    # 基础头部正脸: (8,8)~(15,15)
    base_face = skin.crop((8 * scale, 8 * scale, 16 * scale, 16 * scale))

    # 帽子层正脸: (40,8)~(47,15) (64x64 存在；64x32 视作透明)
    if height >= 16 * scale and width >= 48 * scale:
        hat_face = skin.crop((40 * scale, 8 * scale, 48 * scale, 16 * scale))
        base_face.alpha_composite(hat_face)

    avatar = base_face.resize((output_size, output_size), Image.NEAREST)
    output = BytesIO()
    avatar.save(output, format="PNG")
    return output.getvalue()


def default_steve_head_avatar(output_size: int = 256) -> bytes:
    """
    生成默认 Steve 风格 8x8 正脸平面头像并放大输出。
    """
    # 简化 Steve 正脸配色（8x8）
    palette = [
        ["#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6"],
        ["#6f9fd6", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#6f9fd6"],
        ["#6f9fd6", "#2f2a28", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#2f2a28", "#6f9fd6"],
        ["#6f9fd6", "#2f2a28", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#e7c3a1", "#2f2a28", "#6f9fd6"],
        ["#6f9fd6", "#e7c3a1", "#e7c3a1", "#d39f7d", "#d39f7d", "#e7c3a1", "#e7c3a1", "#6f9fd6"],
        ["#6f9fd6", "#e7c3a1", "#bf8b69", "#bf8b69", "#bf8b69", "#bf8b69", "#e7c3a1", "#6f9fd6"],
        ["#6f9fd6", "#e7c3a1", "#9c6b4c", "#9c6b4c", "#9c6b4c", "#9c6b4c", "#e7c3a1", "#6f9fd6"],
        ["#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6", "#6f9fd6"],
    ]

    head = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    px = head.load()
    for y in range(8):
        for x in range(8):
            color = palette[y][x].lstrip("#")
            px[x, y] = (
                int(color[0:2], 16),
                int(color[2:4], 16),
                int(color[4:6], 16),
                255,
            )

    avatar = head.resize((output_size, output_size), Image.NEAREST)
    output = BytesIO()
    avatar.save(output, format="PNG")
    return output.getvalue()
