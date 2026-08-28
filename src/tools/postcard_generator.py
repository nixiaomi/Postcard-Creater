import os
import io
import requests
import logging
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from coze_coding_dev_sdk import ImageGenerationClient
from coze_coding_dev_sdk.s3 import S3SyncStorage
from coze_coding_utils.runtime_ctx.context import new_context

logger = logging.getLogger(__name__)

# 初始化存储客户端
storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key="",
    secret_key="",
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region="cn-beijing",
)

# 背景图路径 - 使用可靠的路径定位
def _get_background_path() -> str:
    # 优先环境变量
    env_path = os.getenv("COZE_WORKSPACE_PATH")
    candidates = []
    if env_path:
        candidates.append(os.path.join(env_path, "assets", "scnu_postcard_bg.png"))
    # 相对于当前文件位置
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.normpath(os.path.join(current_dir, "..", "..", "assets", "scnu_postcard_bg.png")))
    # 平台部署时的可能路径
    candidates.append("/opt/bytefaas/assets/scnu_postcard_bg.png")
    # 可写目录作为后备
    candidates.append("/tmp/scnu_postcard_bg.png")
    
    for path in candidates:
        if os.path.exists(path):
            return path
    # 默认返回第一个，让调用方判断
    return candidates[0]

# 背景图路径
BACKGROUND_PATH = os.path.normpath(_get_background_path())

# 尝试查找中文字体
def find_chinese_font() -> str:
    """查找系统中可用的中文字体"""
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None

FONT_PATH = find_chinese_font()


def upload_image_to_storage(image: Image.Image, filename: str) -> Tuple[str, str]:
    """
    将PIL图片上传到对象存储
    返回: (file_key, presigned_url)
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    
    file_key = storage.upload_file(
        file_content=buffer.getvalue(),
        file_name=f"postcards/{filename}",
        content_type="image/png",
    )
    
    url = storage.generate_presigned_url(key=file_key, expire_time=86400 * 30)  # 30天有效期
    return file_key, url


def generate_character_image(
    name: str,
    gender: str,
    hobby: str,
    reference_image_url: Optional[str] = None,
    ctx=None
) -> Image.Image:
    """
    生成人物形象图片
    如果有参考图片，则基于参考图片生成动漫风格形象
    否则根据文字描述生成
    """
    client = ImageGenerationClient(ctx=ctx or new_context(method="generate_character"))
    
    # 构建prompt
    gender_desc = "male college student boy" if gender == "male" else "female college student girl" if gender == "female" else "young college student"
    outfit_desc = "casual modern youthful campus outfit, backpack, relaxed standing pose"
    
    if reference_image_url:
        # 有参考照片，生成基于照片的动漫/插画风格人物
        prompt = (
            f"Convert this person photo into a beautiful anime/illustration style character portrait, "
            f"preserving the person's facial features and likeness. "
            f"The character is a {gender_desc} who loves {hobby}. "
            f"{outfit_desc}, cheerful warm smile, energetic. "
            f"IMPORTANT: The image MUST have a COMPLETELY WHITE BACKGROUND, no other elements, just the character. "
            f"Style: clean anime illustration, vibrant warm colors, soft cel-shading, high quality, "
            f"full body or 3/4 body shot, character centered in frame, suitable for placing on a postcard. "
            f"White background only, no shadows on the background."
        )
        response = client.generate(
            prompt=prompt,
            image=reference_image_url,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    else:
        # 无参考照片，根据描述生成
        prompt = (
            f"A beautiful anime/illustration style character portrait of a {gender_desc} university freshman, "
            f"who loves {hobby}. {outfit_desc}, cheerful smiling expression, hopeful for new semester. "
            f"IMPORTANT: The image MUST have a COMPLETELY WHITE BACKGROUND, pure white, no other scene elements, just the character standing alone. "
            f"Style: clean anime illustration, soft warm lighting, vibrant colors, high quality, detailed, "
            f"3/4 body or full body shot, character centered in frame, suitable for placing on a campus postcard. "
            f"White background only, no props in background, no environment, just the character cutout ready for compositing."
        )
        response = client.generate(
            prompt=prompt,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    
    if not response.success:
        raise Exception(f"Image generation failed: {response.error_messages}")
    
    # 下载生成的图片
    img_url = response.image_urls[0]
    img_response = requests.get(img_url, timeout=60)
    img_response.raise_for_status()
    
    character_img = Image.open(io.BytesIO(img_response.content)).convert("RGBA")
    return character_img


def remove_white_background(img: Image.Image, threshold: int = 240) -> Image.Image:
    """去除图片白色背景，转为透明"""
    img = img.convert("RGBA")
    pixels = list(img.getdata())
    
    new_pixels = []
    for px in pixels:
        # 如果像素接近白色，设为透明
        r, g, b = px[0], px[1], px[2]
        if r > threshold and g > threshold and b > threshold:
            new_pixels.append((255, 255, 255, 0))
        else:
            new_pixels.append(px)
    
    img.putdata(new_pixels)
    return img


def add_text_to_image(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[int, int],
    font_size: int,
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
    max_width: Optional[int] = None,
    font_path: Optional[str] = None
):
    """在图片上添加文字，支持自动换行"""
    if font_path and os.path.exists(font_path):
        font = ImageFont.truetype(font_path, font_size)
    elif FONT_PATH:
        font = ImageFont.truetype(FONT_PATH, font_size)
    else:
        font = ImageFont.load_default()
    
    if not max_width:
        draw.text(position, text, font=font, fill=fill)
        return
    
    # 自动换行
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    
    y = position[1]
    line_height = font_size + 10
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = position[0] + (max_width - text_width) // 2  # 居中
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


def create_postcard(
    name: str,
    gender: str,
    hobby: str,
    wish: str,
    reference_image_url: Optional[str] = None,
    ctx=None
) -> Tuple[str, str]:
    """
    创建华师明信片
    设计原则：保持原始背景完整，仅添加人物和底部祝语
    返回: (file_key, download_url)
    """
    logger.info(f"Creating postcard for {name}, gender={gender}, hobby={hobby}")
    
    # 1. 加载背景图
    loaded_bg = False
    bg_path = BACKGROUND_PATH
    if not os.path.exists(bg_path):
        # 尝试其他候选路径
        candidates = [
            "/opt/bytefaas/assets/scnu_postcard_bg.png",
            os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "scnu_postcard_bg.png")),
        ]
        for p in candidates:
            if os.path.exists(p):
                bg_path = p
                loaded_bg = True
                break
        if not loaded_bg:
            # 所有路径都找不到，生成一个
            bg_img = generate_background_image(ctx)
    else:
        bg_img = Image.open(bg_path).convert("RGBA")
    
    bg_w, bg_h = bg_img.size
    logger.info(f"Background size: {bg_w}x{bg_h}")
    
    # 2. 生成人物形象（透明背景）
    character_img = generate_character_image(name, gender, hobby, reference_image_url, ctx)
    character_img = remove_white_background(character_img)
    
    # 3. 调整人物大小 - 不要太大，占画面右下方约35%宽度，避免遮挡太多背景
    char_max_w = int(bg_w * 0.38)
    char_max_h = int(bg_h * 0.60)
    
    char_w, char_h = character_img.size
    scale = min(char_max_w / char_w, char_max_h / char_h)
    new_char_w = int(char_w * scale)
    new_char_h = int(char_h * scale)
    character_img = character_img.resize((new_char_w, new_char_h), Image.Resampling.LANCZOS)
    
    # 人物位置：放在画面右下角区域，垂直方向靠下，水平靠右
    # 给底部祝语留出空间
    char_x = int(bg_w * 0.58)
    char_y = int(bg_h * 0.28)
    
    # 添加柔和阴影
    shadow = Image.new("RGBA", character_img.size, (0, 0, 0, 0))
    shadow.paste(character_img, (0, 0), character_img)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
    shadow_pixels_list = list(shadow.getdata())
    new_shadow_pixels = []
    for px in shadow_pixels_list:
        new_alpha = int(min(px[3], 50) * 0.6)
        new_shadow_pixels.append((0, 0, 0, new_alpha))
    shadow.putdata(new_shadow_pixels)
    
    # 合成阴影
    shadow_layer = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    shadow_layer.paste(shadow, (char_x + 12, char_y + 12), shadow)
    bg_img = Image.alpha_composite(bg_img, shadow_layer)
    
    # 合成人物
    char_layer = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    char_layer.paste(character_img, (char_x, char_y), character_img)
    bg_img = Image.alpha_composite(bg_img, char_layer)
    
    # 4. 添加祝语文字在底部（不添加遮挡条，用描边保证可读性）
    draw = ImageDraw.Draw(bg_img)
    wish_font_size = max(30, int(bg_w / 42))
    
    if FONT_PATH:
        wish_font = ImageFont.truetype(FONT_PATH, wish_font_size)
    else:
        wish_font = ImageFont.load_default()
    
    # 祝语放在底部中央，自动换行
    wish_max_width = int(bg_w * 0.80)
    # 计算文字位置，底部留边距
    bottom_margin = int(bg_h * 0.06)
    
    # 手动换行
    lines = []
    current_line = ""
    for char in wish:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=wish_font)
        if bbox[2] - bbox[0] > wish_max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    
    line_height = wish_font_size + 8
    total_text_height = len(lines) * line_height
    start_y = bg_h - bottom_margin - total_text_height
    
    # 绘制带描边的文字，无需背景条
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=wish_font)
        text_width = bbox[2] - bbox[0]
        x = (bg_w - text_width) // 2
        y = start_y + i * line_height
        # 多层描边保证在各种背景上都清晰
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, font=wish_font, fill=(20, 40, 80, 220))
        # 主文字
        draw.text((x, y), line, font=wish_font, fill=(255, 255, 255, 250))
    
    # 右下角添加小字水印
    small_font_size = max(14, int(bg_w / 90))
    if FONT_PATH:
        small_font = ImageFont.truetype(FONT_PATH, small_font_size)
        draw.text(
            (bg_w - 280, bg_h - 25),
            "华南师范大学 · 人工智能学院",
            font=small_font,
            fill=(255, 255, 255, 160)
        )
    
    # 转换为RGB保存
    final_img = bg_img.convert("RGB")
    
    # 5. 上传到对象存储
    import time
    filename = f"scnu_postcard_{name}_{int(time.time())}.png"
    file_key, url = upload_image_to_storage(final_img, filename)
    
    logger.info(f"Postcard created successfully: {url}")
    return file_key, url


def generate_background_image(ctx=None) -> Image.Image:
    """生成华师风格的明信片背景"""
    client = ImageGenerationClient(ctx=ctx or new_context(method="generate_bg"))
    
    prompt = (
        "South China Normal University campus postcard background photography. "
        "Beautiful academic hall building (学术厅) in light gray/white color, "
        "pink kapok flowers (异木棉/美丽异木棉) blooming on tree branches in foreground, "
        "vibrant green leaves, bright blue sky with soft white clouds, "
        "sunny day warm golden sunlight, dreamy bokeh light effects, "
        "oval-shaped vignette frame in center showing the campus scene, "
        "soft light blue and white gradient at bottom area for text, "
        "small twinkling star light particles, "
        "At top left: university logo placeholder area and Chinese text '华南师范大学 人工智能学院' in elegant dark blue calligraphy style, "
        "small decorative yellow and blue dots near the text. "
        "The right side and bottom should have clear space for placing character and text. "
        "High quality professional photography, postcard composition, warm youthful campus atmosphere, "
        "clean composition, not too cluttered, 3:2 or 16:10 aspect ratio."
    )
    
    response = client.generate(
        prompt=prompt,
        size="2K",
        watermark=False
    )
    
    if not response.success:
        raise Exception(f"Background generation failed: {response.error_messages}")
    
    img_url = response.image_urls[0]
    img_response = requests.get(img_url, timeout=60)
    img_response.raise_for_status()
    
    bg_img = Image.open(io.BytesIO(img_response.content)).convert("RGBA")
    
    # 保存到本地 - 优先保存到可写目录/tmp，避免只读文件系统问题
    save_paths = [
        BACKGROUND_PATH,
        "/tmp/scnu_postcard_bg.png",
    ]
    for save_path in save_paths:
        try:
            save_dir = os.path.dirname(save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            bg_img.convert("RGB").save(save_path, "PNG", quality=95)
            logger.info(f"Background saved to: {save_path}")
            break
        except (OSError, IOError) as e:
            logger.warning(f"Cannot save to {save_path}: {e}")
            continue
    
    return bg_img
