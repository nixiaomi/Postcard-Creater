import logging
from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from tools.digital_id_generator import generate_digital_id_card

logger = logging.getLogger(__name__)


@tool
def create_digital_id(
    name_pinyin: str,
    student_id: str,
    major_en: str,
    message_en: str,
    photo_key: str = ""
) -> str:
    """
    在用户确认所有信息正确后，调用此工具生成华南师范大学人工智能学院2026新生数字身份卡。
    
    **调用时机**：
    必须在用户确认所有信息正确之后才能调用！
    调用前必须严格按照流程收集完 Name/Student ID/Major/Message to Myself 四项信息并展示给用户确认。
    
    **参数说明**：
    - name_pinyin: 用户中文姓名转换后的标准拼音，格式为"姓 名"，首字母大写，例如 Zhang Wei
    - student_id: 用户的学号，必须原样保留用户输入的数字/字符，不得修改
    - major_en: 用户输入的中文专业名称转换后的标准英文专业名称
    - message_en: 用户寄语翻译为自然流畅、有文学感的英文，保留原意和情绪，青春成长风格
    - photo_key: 用户上传的照片key，如果用户没有上传照片则传空字符串
    
    **返回**：
    生成成功后返回身份卡的预览图和下载链接。
    """
    ctx = request_context.get() or new_context(method="create_digital_id")
    
    # 处理参考图片URL
    reference_url = None
    if photo_key:
        from tools.digital_id_generator import storage
        reference_url = storage.generate_presigned_url(key=photo_key, expire_time=3600)
    
    try:
        file_key, url = generate_digital_id_card(
            name_pinyin=name_pinyin,
            student_id=student_id,
            major_en=major_en,
            message_en=message_en,
            reference_image_url=reference_url,
            ctx=ctx
        )
        return f"""
✅ 你的华南师范大学2026新生数字身份卡已生成成功！

📷 预览：
![Digital ID Card]({url})

⬇️ 下载链接（30天有效）：
[点击下载高清PNG]({url})

欢迎来到华南师范大学人工智能学院，开启你的新旅程！🎉
        """.strip()
    except Exception as e:
        logger.error(f"Generate digital ID failed: {str(e)}", exc_info=True)
        return f"抱歉，生成数字身份卡时遇到错误：{str(e)}，请稍后重试。"
