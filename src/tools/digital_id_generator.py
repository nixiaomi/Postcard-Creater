import os
import io
import logging
from typing import Optional, Tuple, List
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
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
    """查找可用中文字体"""
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def find_bold_font(size: int) -> ImageFont.FreeTypeFont:
    """查找可用加粗字体"""
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return find_font(size)


def draw_text_glow(
    draw: ImageDraw.ImageDraw,
    pos: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
    glow_color: Tuple[int, int, int, int] = (0, 255, 255, 100),
    glow_radius: int = 2
):
    """绘制发光文字"""
    x, y = pos
    for dx in range(-glow_radius, glow_radius + 1):
        for dy in range(-glow_radius, glow_radius + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
    draw.text(pos, text, font=font, fill=fill)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """英文自动换行"""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + (" " if current else "") + word
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def generate_digital_id_card(
    name_pinyin: str,
    student_id: str,
    major_en: str,
    message_en: str,
    reference_image_url: Optional[str] = None,
    ctx=None
) -> Tuple[str, str]:
    """
    严格按照ROLE规范生成华师2026新生数字身份卡
    布局：HEADER(10%) + MAIN(60%)(左Avatar40%+右Information60%) + MESSAGE(30%)
    三级视觉层级：NAME最大 → STUDENT ID/MAJOR中等 → SCHOOL/COLLEGE较小
    """
    ctx = ctx or new_context(method="generate_digital_id")
    client = ImageGenerationClient(ctx=ctx)
    
    logger.info(f"Generating digital ID card: {name_pinyin}, ID: {student_id}")
    
    # ========== 1. 生成基础模板（包含完整卡片设计和头像） ==========
    if reference_image_url:
        # 使用用户上传照片做参考生成数字人
        prompt = (
            "16:9 horizontal futuristic holographic digital student ID card template, NO TEXT AT ALL. "
            "THREE SECTION LAYOUT: "
            "TOP 10%: thin header area with subtle glowing border decoration, empty for title. "
            "MIDDLE 60% split into LEFT 40% and RIGHT 60%: "
            "LEFT 40%: large circular holographic avatar frame with dual neon cyan and magenta glowing rings, "
            "inside convert reference photo person into premium 3D digital avatar, PRESERVE original facial features, "
            "face shape, hairstyle, skin tone and personal气质, recognizable as the same person, "
            "slight anime style, soft cinematic lighting, youthful, front-facing bust portrait centered, "
            "subtle HUD scan lines, digital particles around circle, NOT TOO MUCH DECORATION. "
            "RIGHT 60%: empty clean transparent glass surface ready for text information, subtle grid lines. "
            "BOTTOM 30%: separate semi-transparent glass panel area for message, subtle neon divider line above. "
            "Overall card: horizontal floating transparent glass morphism card, holographic neon borders in cyan (#00ffff) and magenta (#ff00ff), "
            "digital circuit patterns, sci-fi UI frame, premium elegant, NOT CHEAP RGB GAMING STYLE. "
            "Background: dark futuristic university campus night, low contrast, starry sky, building silhouettes, "
            "subtle neon bokeh, holographic particles, depth of field blur, atmosphere only, does NOT distract from card. "
            "Style: premium cinematic glass morphism, clean elegant cyberpunk, 8k ultra detailed, ABSOLUTELY NO TEXT."
        )
        response = client.generate(
            prompt=prompt,
            image=reference_image_url,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    else:
        # 无参考照片，生成标准模板
        prompt = (
            "16:9 horizontal futuristic holographic digital student ID card template, NO TEXT AT ALL. "
            "THREE SECTION LAYOUT: "
            "TOP 10%: thin header area with subtle glowing border decoration, empty for title. "
            "MIDDLE 60% split into LEFT 40% and RIGHT 60%: "
            "LEFT 40%: large circular holographic avatar frame with dual neon cyan and magenta glowing rings, "
            "inside: beautiful 18-year-old asian university freshman 3D digital avatar, friendly gentle smile, "
            "refined premium digital human, slight anime style, soft cinematic lighting, youthful natural, "
            "front-facing bust portrait centered in circle, subtle HUD particles around. "
            "RIGHT 60%: empty clean transparent glass surface for information. "
            "BOTTOM 30%: separate semi-transparent glass panel area for personal message, subtle neon divider line. "
            "Overall: horizontal floating glass morphism card, holographic projection, neon cyan and magenta borders, "
            "digital circuit patterns, premium elegant sci-fi frame. "
            "Background: dark futuristic campus night, low contrast, starry sky, building silhouettes, neon bokeh, particles, "
            "bokeh blur, dark vignette edges, ATMOSPHERE ONLY. "
            "Style: premium cinematic glass morphism, clean elegant, 8k, NO TEXT."
        )
        response = client.generate(
            prompt=prompt,
            size="2K",
            watermark=False,
            model="doubao-seedream-5-0-260128"
        )
    
    if not response.success:
        raise Exception(f"Image generation failed: {response.error_messages}")
    
    # 下载并裁剪为16:9
    img_url = response.image_urls[0]
    img_resp = requests.get(img_url, timeout=60)
    img_resp.raise_for_status()
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    
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
    
    # ========== 严格按照ROLE规范的三级网格布局 ==========
    # 边距（卡片内安全区域）
    pad = int(w * 0.035)
    left_info_x = int(w * 0.42)  # 信息区左边界
    right_x = w - pad
    
    # 分区高度：HEADER 10% | MAIN 60% | MESSAGE 30%
    header_h = int(h * 0.10)
    main_h = int(h * 0.60)
    msg_h = int(h * 0.30)
    
    header_y_start = int(h * 0.02)
    main_y_start = header_h + int(h * 0.01)
    msg_y_start = header_h + main_h + int(h * 0.01)
    
    # ---------- HEADER 区域（顶部10%）----------
    header_label_font = find_font(int(h * 0.035))
    header_year_font = find_bold_font(int(h * 0.040))
    decor_font = find_font(int(h * 0.016))
    
    # 左侧：2026 NEW STUDENT
    draw_text_glow(
        draw, (pad, header_y_start + int(h*0.02)),
        "2026  ·  NEW STUDENT  ·  DIGITAL ID",
        header_label_font,
        fill=(255, 255, 255, 230),
        glow_color=(0, 255, 255, 80),
        glow_radius=2
    )
    # 右侧装饰
    draw.text((right_x - int(w*0.18), header_y_start + int(h*0.03)), 
              "◉ SYSTEM ONLINE  ▣ INITIALIZED", font=decor_font, fill=(0, 255, 255, 130))
    
    # Header底部细分割线
    draw.line([(pad, header_h - 2), (right_x, header_h - 2)], 
              fill=(0, 255, 255, 80), width=1)
    
    # ---------- 右侧 INFORMATION 区域（MAIN区右侧60%，三级视觉层级）----------
    info_y = main_y_start + int(h * 0.03)
    
    # ===== LEVEL 1: NAME（最大最醒目，最多1行）=====
    label_l1_font = find_font(int(h * 0.022))  # 标签小
    value_l1_font = find_bold_font(int(h * 0.068))  # 姓名最大
    
    draw.text((left_info_x, info_y), "NAME", font=label_l1_font, fill=(0, 255, 255, 200))
    info_y += int(h * 0.028)
    draw_text_glow(
        draw, (left_info_x, info_y), name_pinyin, value_l1_font,
        fill=(255, 255, 255, 250),
        glow_color=(255, 0, 255, 70),
        glow_radius=3
    )
    info_y += int(h * 0.075)
    
    # 分割线（NAME之后）
    draw.line([(left_info_x, info_y), (right_x, info_y)], 
              fill=(0, 255, 255, 100), width=1)
    info_y += int(h * 0.020)
    
    # ===== LEVEL 2: STUDENT ID + MAJOR（中等字号）=====
    label_l2_font = find_font(int(h * 0.020))
    value_l2_font = find_bold_font(int(h * 0.040))
    
    # STUDENT ID
    draw.text((left_info_x, info_y), "STUDENT ID", font=label_l2_font, fill=(0, 255, 255, 200))
    info_y += int(h * 0.025)
    draw_text_glow(
        draw, (left_info_x, info_y), student_id, value_l2_font,
        fill=(255, 255, 255, 240),
        glow_color=(0, 255, 255, 50),
        glow_radius=1
    )
    info_y += int(h * 0.050)
    
    # MAJOR（最多2行）
    draw.text((left_info_x, info_y), "MAJOR", font=label_l2_font, fill=(0, 255, 255, 200))
    info_y += int(h * 0.025)
    major_lines = wrap_text(draw, major_en, value_l2_font, right_x - left_info_x)
    for i, line in enumerate(major_lines[:2]):
        draw.text((left_info_x, info_y + i * int(h*0.043)), line, font=value_l2_font, fill=(255, 255, 255, 240))
    info_y += min(len(major_lines), 2) * int(h * 0.043) + int(h * 0.018)
    
    # 分割线（LEVEL 2之后）
    draw.line([(left_info_x, info_y), (right_x, info_y)], 
              fill=(0, 255, 255, 100), width=1)
    info_y += int(h * 0.018)
    
    # ===== LEVEL 3: SCHOOL + COLLEGE（较小字号，机构信息）=====
    label_l3_font = find_font(int(h * 0.018))
    value_l3_font = find_font(int(h * 0.030))
    
    # SCHOOL
    draw.text((left_info_x, info_y), "SCHOOL", font=label_l3_font, fill=(0, 255, 255, 180))
    info_y += int(h * 0.022)
    school_lines = wrap_text(draw, "South China Normal University", value_l3_font, right_x - left_info_x)
    for i, line in enumerate(school_lines[:2]):
        draw.text((left_info_x, info_y + i * int(h*0.033)), line, font=value_l3_font, fill=(220, 240, 255, 210))
    info_y += min(len(school_lines), 2) * int(h * 0.033) + int(h * 0.012)
    
    # COLLEGE
    draw.text((left_info_x, info_y), "COLLEGE", font=label_l3_font, fill=(255, 0, 255, 180))
    info_y += int(h * 0.022)
    college_lines = wrap_text(draw, "School of Artificial Intelligence", value_l3_font, right_x - left_info_x)
    for i, line in enumerate(college_lines[:2]):
        draw.text((left_info_x, info_y + i * int(h*0.033)), line, font=value_l3_font, fill=(255, 220, 255, 210))
    
    # ---------- 底部 MESSAGE 区域（占30%高度，独立玻璃面板）----------
    # 区域顶部霓虹分割线
    draw.line([(pad, msg_y_start - 2), (right_x, msg_y_start - 2)], 
              fill=(255, 0, 255, 100), width=2)
    
    msg_title_font = find_bold_font(int(h * 0.024))
    msg_font = find_font(int(h * 0.030))
    
    msg_title_y = msg_y_start + int(h * 0.025)
    draw.text((pad + int(w*0.02), msg_title_y), "MESSAGE TO MYSELF", 
              font=msg_title_font, fill=(255, 0, 255, 200))
    
    # 寄语文字（左对齐，最多4行，保持足够留白）
    msg_text_y = msg_title_y + int(h * 0.038)
    max_msg_width = w - pad*2 - int(w*0.04)
    msg_lines = wrap_text(draw, message_en, msg_font, max_msg_width)
    line_height = int(h * 0.038)
    for i, line in enumerate(msg_lines[:4]):
        draw.text((pad + int(w*0.02), msg_text_y + i * line_height), 
                  line, font=msg_font, fill=(255, 245, 255, 230))
    
    # 左下角/右下角装饰
    draw.text((pad, h - int(h*0.045)), "◈ FUTURE · CAMPUS · 2026 ◈", 
              font=decor_font, fill=(0, 255, 255, 120))
    
    # ========== 保存并上传 ==========
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
    logger.info(f"Digital ID card generated: {download_url}")
    
    return file_key, download_url
