import os
import io
import logging
from typing import Optional, Tuple
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from coze_coding_dev_sdk import ImageGenerationClient
from coze_coding_dev_sdk.s3 import S3SyncStorage
from coze_coding_utils.runtime_ctx.context import new_context

logger = logging.getLogger(__name__)

storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key="",
    secret_key="",
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region="cn-beijing",
)


def find_font(size: int) -> ImageFont.FreeTypeFont:
    """查找可用字体"""
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_text_with_glow(
    draw: ImageDraw.ImageDraw,
    pos: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
    glow_color: Tuple[int, int, int, int] = (0, 255, 255, 120),
    glow_radius: int = 3
):
    """绘制带发光效果的文字"""
    x, y = pos
    for dx in range(-glow_radius, glow_radius + 1):
        for dy in range(-glow_radius, glow_radius + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
    draw.text(pos, text, font=font, fill=fill)


def generate_digital_id_card(
    name_pinyin: str,
    student_id: str,
    major_en: str,
    message_en: str,
    reference_image_url: Optional[str] = None,
    ctx=None
) -> Tuple[str, str]:
    """
    生成华师2026新生数字身份卡
    布局严格遵循：左侧头像(40%) + 右侧信息(60%) + 底部寄语
    返回: (file_key, download_url)
    """
    ctx = ctx or new_context(method="generate_digital_id")
    client = ImageGenerationClient(ctx=ctx)
    
    logger.info(f"Generating digital ID card for {name_pinyin}, ID: {student_id}, Major: {major_en}")
    
    # ========== 1. 生成基础模板（包含头像和整体设计） ==========
    if reference_image_url:
        # 有用户上传照片，使用图生图生成数字人头像
        prompt = (
            "16:9 horizontal futuristic holographic digital student ID card design, NO TEXT. "
            "LEFT 40%: large circular glowing avatar frame with neon cyan and magenta rings, "
            "inside the circle: convert the reference photo person into a refined 3D digital avatar, "
            "preserve original facial features, face shape, hairstyle, skin tone and personal气质, "
            "slight anime style, premium digital human look, soft cinematic lighting, youthful, natural, "
            "front-facing bust portrait centered in circle, holographic scan lines, digital particles around. "
            "RIGHT 60%: empty clean transparent glass morphism panel ready for information, subtle HUD grid lines. "
            "Floating glass card overall with neon cyan (#00ffff) and magenta (#ff00ff) glowing borders, "
            "digital circuit patterns, futuristic sci-fi UI frame. "
            "Background: dark futuristic university campus at night, starry sky, futuristic building silhouettes, "
            "neon bokeh, digital particles, volumetric light, depth of field blur. "
            "Style: premium cinematic, glass morphism, cyberpunk but clean elegant, "
            "8k ultra detailed, NO TEXT NO WORDS anywhere."
        )
        response = client.generate(
            prompt=prompt,
            image=reference_image_url,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    else:
        # 无参考照片，生成标准数字人模板
        prompt = (
            "16:9 horizontal futuristic holographic digital student ID card design, NO TEXT. "
            "LEFT 40%: large circular glowing avatar frame with dual neon cyan and magenta rings, "
            "inside: beautiful 18-year-old asian university freshman digital avatar, friendly gentle expression, "
            "refined 3D digital character, slight anime style, premium digital human, soft cinematic lighting, "
            "youthful, front-facing bust portrait centered, holographic particles and scan lines around circle. "
            "RIGHT 60%: empty clean glass surface for information display. "
            "Overall: horizontal floating glass card, transparent glass morphism, holographic projection effect, "
            "neon glowing borders in cyan blue and magenta pink, digital circuit patterns, sci-fi UI frame. "
            "Background: dark futuristic campus night, starry sky, building silhouettes, neon bokeh, particles, "
            "volumetric light, bokeh blur, dark edges. "
            "Style: premium cinematic, glass morphism, clean elegant, 8k, NO TEXT."
        )
        response = client.generate(
            prompt=prompt,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    
    if not response.success:
        raise Exception(f"Image generation failed: {response.error_messages}")
    
    # 下载基础图
    img_url = response.image_urls[0]
    img_resp = requests.get(img_url, timeout=60)
    img_resp.raise_for_status()
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    
    # 裁剪为16:9横版
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = max(0, (h - new_h) // 2)
        img = img.crop((0, top, w, top + new_h))
    
    w, h = img.size
    draw = ImageDraw.Draw(img)
    
    # ========== 2. 添加文字信息（电子名片内部区域） ==========
    right_x = int(w * 0.42)
    margin_right = int(w * 0.05)
    
    # 字体大小（整体调小，确保在名片范围内）
    label_size = int(h * 0.026)
    value_name_size = int(h * 0.060)
    value_size = int(h * 0.036)
    decor_size = int(h * 0.018)
    
    label_font = find_font(label_size)
    name_font = find_font(value_name_size)
    value_font = find_font(value_size)
    decor_font = find_font(decor_size)
    msg_title_font = find_font(int(h * 0.024))
    msg_font = find_font(int(h * 0.028))
    
    # 顶部装饰文字（名片内部右上角）
    draw.text((w - int(w*0.25), int(h*0.10)), "SYSTEM ONLINE · 2026", 
              font=decor_font, fill=(0, 255, 255, 150))
    
    # 右侧信息列表（上移，紧凑排布，放在电子名片玻璃区域内）
    info_start_y = int(h * 0.15)
    line_gap = int(h * 0.078)
    
    info_items = [
        ("NAME", name_pinyin, True),
        ("STUDENT ID", student_id, False),
        ("MAJOR", major_en, False),
        ("SCHOOL", "South China Normal University", False),
        ("COLLEGE", "School of Artificial Intelligence", False),
    ]
    
    for i, (label, value, is_name) in enumerate(info_items):
        y = info_start_y + i * line_gap
        # 标签（青色小字）
        draw.text((right_x, y), label, font=label_font, fill=(0, 255, 255, 210))
        # 值（白色发光字，NAME最醒目但大小合适）
        f = name_font if is_name else value_font
        glow_r = 3 if is_name else 1
        glow_c = (255, 0, 255, 70) if is_name else (0, 255, 255, 60)
        draw_text_with_glow(
            draw, (right_x, y + int(h*0.028)), value, f,
            fill=(255, 255, 255, 250),
            glow_color=glow_c,
            glow_radius=glow_r
        )
    
    # 分割线（信息和寄语之间）
    line_y = info_start_y + len(info_items) * line_gap - int(h*0.015)
    draw.line([(right_x, line_y), (w - margin_right, line_y)], fill=(0, 255, 255, 120), width=1)
    
    # ========== 3. 底部寄语区域（紧凑，控制长度在15字内单行展示） ==========
    msg_y = line_y + int(h * 0.02)
    draw.text((right_x, msg_y), "MESSAGE TO MYSELF", font=msg_title_font, fill=(255, 0, 255, 210))
    
    # 自动换行处理英文寄语
    words = message_en.split()
    lines = []
    current_line = ""
    max_width = w - right_x - margin_right
    for word in words:
        test = current_line + (" " if current_line else "") + word
        bbox = draw.textbbox((0, 0), test, font=msg_font)
        if bbox[2] - bbox[0] > max_width and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)
    
    msg_text_y = msg_y + int(h * 0.032)
    line_height = int(h * 0.034)
    for i, line in enumerate(lines[:2]):  # 最多2行，寄语控制在15字内基本单行
        draw.text((right_x, msg_text_y + i * line_height), line, font=msg_font, fill=(255, 240, 255, 230))
    
    # 底部装饰文字（名片内底部）
    scan_y = h - int(h*0.07)
    draw.text((right_x, scan_y), "◉ SCAN  ▣ ID VERIFIED  ◈ NEW JOURNEY", 
              font=decor_font, fill=(0, 255, 255, 130))
    
    # ========== 4. 保存并上传 ==========
    final_img = img.convert("RGB")
    buf = io.BytesIO()
    final_img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    
    import time
    safe_name = name_pinyin.replace(" ", "_")
    file_key = storage.upload_file(
        file_content=buf.getvalue(),
        file_name=f"digital_id_{safe_name}_{int(time.time())}.png",
        content_type="image/png"
    )
    
    download_url = storage.generate_presigned_url(key=file_key, expire_time=86400 * 30)
    logger.info(f"Digital ID card generated successfully: {download_url}")
    
    return file_key, download_url
