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

# 背景图路径
BACKGROUND_PATH = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"), "assets", "scnu_postcard_bg.png")

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
    gender_desc = "男生" if gender == "male" else "女生" if gender == "female" else "大学生"
    
    if reference_image_url:
        # 有参考照片，生成基于照片的动漫/插画风格人物
        prompt = (
            f"Convert this photo into a beautiful anime/illustration style character portrait. "
            f"The character is a {gender_desc} university student named {name} who loves {hobby}. "
            f"Style: warm, vibrant, youth campus style, soft lighting, detailed, high quality, "
            f"full body or half body portrait, transparent background, pure white background, "
            f"cheerful expression, modern college student outfit, South China Normal University vibe. "
            f"The character should look energetic and hopeful for the new semester."
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
            f"A beautiful anime/illustration style character portrait of a {gender_desc} university student. "
            f"Name: {name}, Hobby: {hobby}. "
            f"Style: warm, vibrant, youth campus style, soft lighting, detailed, high quality, "
            f"full body or half body portrait, transparent background or pure white background, "
            f"cheerful smiling expression, modern casual college outfit, backpack, "
            f"energetic and hopeful feeling for new semester, "
            f"standing pose, South China Normal University campus atmosphere, pink flowers and green trees in vibe. "
            f"Make the character cute and appealing."
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
    返回: (file_key, download_url)
    """
    logger.info(f"Creating postcard for {name}, gender={gender}, hobby={hobby}")
    
    # 1. 加载或生成背景图
    if os.path.exists(BACKGROUND_PATH):
        bg_img = Image.open(BACKGROUND_PATH).convert("RGBA")
    else:
        # 如果背景图不存在，生成一个华师风格的背景
        bg_img = generate_background_image(ctx)
    
    # 确保背景图尺寸合适
    bg_w, bg_h = bg_img.size
    logger.info(f"Background size: {bg_w}x{bg_h}")
    
    # 2. 生成人物形象
    character_img = generate_character_image(name, gender, hobby, reference_image_url, ctx)
    character_img = remove_white_background(character_img)
    
    # 3. 调整人物大小并放置到中间偏右位置
    # 人物区域：中间到右边，约占背景宽度的50%，高度70%
    char_max_w = int(bg_w * 0.45)
    char_max_h = int(bg_h * 0.65)
    
    char_w, char_h = character_img.size
    scale = min(char_max_w / char_w, char_max_h / char_h)
    new_char_w = int(char_w * scale)
    new_char_h = int(char_h * scale)
    character_img = character_img.resize((new_char_w, new_char_h), Image.Resampling.LANCZOS)
    
    # 人物位置：水平方向在右侧55%位置开始，垂直方向在25%位置
    char_x = int(bg_w * 0.52)
    char_y = int(bg_h * 0.20)
    
    # 添加轻微阴影效果
    shadow = Image.new("RGBA", character_img.size, (0, 0, 0, 0))
    shadow.paste(character_img, (0, 0), character_img)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    
    # 将阴影颜色改为黑色半透明
    shadow = shadow.convert("RGBA")
    shadow_pixels_list = list(shadow.getdata())
    new_shadow_pixels = []
    for px in shadow_pixels_list:
        new_alpha = min(px[3], 70)
        new_shadow_pixels.append((0, 0, 0, new_alpha))
    shadow.putdata(new_shadow_pixels)
    
    # 先绘制阴影，再绘制人物
    shadow_layer = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    shadow_layer.paste(shadow, (char_x + 8, char_y + 8), shadow)
    bg_img = Image.alpha_composite(bg_img, shadow_layer)
    
    # 粘贴人物
    char_layer = Image.new("RGBA", bg_img.size, (0, 0, 0, 0))
    char_layer.paste(character_img, (char_x, char_y), character_img)
    bg_img = Image.alpha_composite(bg_img, char_layer)
    
    # 4. 添加名字标签（在人物旁边）
    draw = ImageDraw.Draw(bg_img)
    
    # 名字区域 - 左下方
    name_font_size = max(36, int(bg_w / 35))
    wish_font_size = max(28, int(bg_w / 45))
    
    # 添加半透明装饰条放名字和祝语
    # 底部区域放祝语
    bottom_bar_h = int(bg_h * 0.18)
    bottom_bar = Image.new("RGBA", (bg_w, bottom_bar_h), (100, 149, 237, 160))  # 华师蓝
    bg_img.paste(bottom_bar, (0, bg_h - bottom_bar_h), bottom_bar)
    
    # 左侧信息区域 - 名字
    info_x = int(bg_w * 0.08)
    info_y = int(bg_h * 0.35)
    
    # 名字背景装饰
    name_text = f"姓名：{name}"
    if FONT_PATH:
        name_font = ImageFont.truetype(FONT_PATH, name_font_size)
    else:
        name_font = ImageFont.load_default()
    
    # 绘制名字
    draw.text((info_x, info_y), name_text, font=name_font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 51, 102, 255))
    
    # 爱好
    hobby_text = f"爱好：{hobby}"
    if FONT_PATH:
        hobby_font = ImageFont.truetype(FONT_PATH, int(name_font_size * 0.7))
    else:
        hobby_font = ImageFont.load_default()
    draw.text((info_x, info_y + name_font_size + 20), hobby_text, font=hobby_font, fill=(255, 255, 255, 240), stroke_width=1, stroke_fill=(0, 51, 102, 200))
    
    # 底部祝语 - 居中
    wish_max_width = int(bg_w * 0.85)
    wish_y = bg_h - bottom_bar_h + 25
    add_text_to_image(
        bg_img,
        draw,
        f" {wish}",
        (int(bg_w * 0.075), wish_y),
        wish_font_size,
        fill=(255, 255, 255, 255),
        max_width=wish_max_width,
        font_path=FONT_PATH
    )
    
    # 5. 添加华师logo文字（左上角已有，这里添加小水印）
    small_font_size = max(16, int(bg_w / 80))
    if FONT_PATH:
        small_font = ImageFont.truetype(FONT_PATH, small_font_size)
    else:
        small_font = ImageFont.load_default()
    draw.text(
        (bg_w - 250, bg_h - 40),
        "华南师范大学 · 人工智能学院",
        font=small_font,
        fill=(255, 255, 255, 180)
    )
    
    # 转换为RGB保存
    final_img = bg_img.convert("RGB")
    
    # 6. 上传到对象存储
    import time
    filename = f"scnu_postcard_{name}_{int(time.time())}.png"
    file_key, url = upload_image_to_storage(final_img, filename)
    
    logger.info(f"Postcard created successfully: {url}")
    return file_key, url


def generate_background_image(ctx=None) -> Image.Image:
    """生成华师风格的明信片背景"""
    client = ImageGenerationClient(ctx=ctx or new_context(method="generate_bg"))
    
    prompt = (
        "A beautiful postcard background of South China Normal University campus. "
        "Scene: Academic building (学术厅) surrounded by pink kapok flowers (异木棉) blooming on trees, "
        "blue sky with white clouds, bright sunny day, warm campus atmosphere. "
        "Style: photo-realistic, vibrant colors, dreamy soft light, bokeh effects, light blue and white gradient overlay, "
        "sparkling light effects. "
        "Top left corner has text area reserved for university logo and name. "
        "Composition: oval frame in middle showing the campus scene, bottom area is light blue gradient for text. "
        "University name '华南师范大学 人工智能学院' in calligraphy style at top. "
        "Decorative elements: small yellow and blue dots at top left, stars and light particles. "
        "High quality, postcard design, 16:9 or similar ratio."
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
    
    # 保存到本地
    os.makedirs(os.path.dirname(BACKGROUND_PATH), exist_ok=True)
    bg_img.convert("RGB").save(BACKGROUND_PATH, "PNG", quality=95)
    
    return bg_img
