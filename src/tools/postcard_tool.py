import os
import logging
from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

from tools.postcard_generator import create_postcard
from tools.file_upload import save_uploaded_file

logger = logging.getLogger(__name__)


@tool
def generate_postcard(
    name: str,
    gender: str,
    hobby: str,
    wish: str,
    photo_key: str = ""
) -> str:
    """
    为华师学子生成专属开学纪念明信片。当用户提供了姓名、性别、爱好、开学祝语后调用此工具。
    如果用户上传了照片，photo_key传入照片的对象存储key；没有传照片则留空字符串。
    
    Args:
        name: 用户姓名，例如"张三"
        gender: 性别，"male"表示男生，"female"表示女生，"other"表示其他
        hobby: 用户的爱好，简短描述，例如"打篮球、阅读"
        wish: 用户写的开学祝语，不超过100字
        photo_key: 可选，用户上传照片后获得的文件key，没有则传空字符串
    """
    try:
        ctx = request_context.get() or new_context(method="generate_postcard_tool")
        
        logger.info(f"Generating postcard via tool: name={name}, gender={gender}")
        
        # 如果有photo_key，转换为可访问的URL
        photo_url = None
        if photo_key:
            from coze_coding_dev_sdk.s3 import S3SyncStorage
            storage = S3SyncStorage(
                endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
                access_key="",
                secret_key="",
                bucket_name=os.getenv("COZE_BUCKET_NAME"),
                region="cn-beijing",
            )
            photo_url = storage.generate_presigned_url(key=photo_key, expire_time=3600)
        
        file_key, download_url = create_postcard(
            name=name,
            gender=gender,
            hobby=hobby,
            wish=wish,
            reference_image_url=photo_url,
            ctx=ctx
        )
        
        # 返回结果，包含图片Markdown和下载链接
        result = (
            f"✅ 明信片生成成功！\n\n"
            f"![{name}的华师专属明信片]({download_url})\n\n"
            f"💾 [点击下载高清明信片]({download_url})\n\n"
            f"---\n"
            f"📮 **{name}**的专属明信片制作完成，长按图片或点击链接即可保存！"
        )
        return result
        
    except Exception as e:
        logger.exception(f"Postcard generation failed: {e}")
        return f"❌ 明信片生成失败：{str(e)}\n\n请稍后重试，或者检查一下网络连接。"
