import os
import io
import uuid
import logging
from typing import Tuple
from PIL import Image
from coze_coding_dev_sdk.s3 import S3SyncStorage

logger = logging.getLogger(__name__)

storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key="",
    secret_key="",
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region="cn-beijing",
)


def save_uploaded_file(file_content: bytes, original_filename: str) -> Tuple[str, str]:
    """
    保存用户上传的文件到对象存储
    返回: (file_key, public_url)
    """
    # 确定文件扩展名
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
        ext = '.jpg'  # 默认
    
    # 处理图片：压缩和验证
    try:
        img = Image.open(io.BytesIO(file_content))
        # 如果是RGBA模式，转换为RGB
        if img.mode == 'RGBA':
            # 创建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 调整大小，最大边不超过2048
        max_size = 2048
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        
        # 保存为JPEG
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        file_content = buffer.getvalue()
        content_type = "image/jpeg"
        ext = '.jpg'
    except Exception as e:
        logger.warning(f"Image processing failed, using original: {e}")
        content_type = "image/jpeg"
    
    filename = f"uploads/user_photo_{uuid.uuid4().hex[:8]}{ext}"
    
    file_key = storage.upload_file(
        file_content=file_content,
        file_name=filename,
        content_type=content_type,
    )
    
    # 生成访问URL（1小时有效期）
    url = storage.generate_presigned_url(key=file_key, expire_time=3600)
    
    logger.info(f"File uploaded: {file_key}")
    return file_key, url
