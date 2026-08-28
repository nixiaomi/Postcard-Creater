import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from coze_coding_utils.runtime_ctx.context import new_context

# 添加src到路径
workspace = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
sys.path.insert(0, os.path.join(workspace, "src"))

from tools.postcard_generator import create_postcard
from tools.file_upload import save_uploaded_file

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="华师明信片制作智能体", description="华南师范大学AI明信片生成器")

# 静态文件和模板
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 明信片制作表单"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    """上传用户照片"""
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB限制
            raise HTTPException(status_code=400, detail="文件大小不能超过10MB")
        
        file_key, url = save_uploaded_file(content, file.filename)
        return JSONResponse({
            "success": True,
            "file_key": file_key,
            "url": url
        })
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.post("/api/generate-postcard")
async def generate_postcard(
    name: str = Form(...),
    gender: str = Form(...),
    hobby: str = Form(...),
    wish: str = Form(...),
    photo_url: str = Form(None)
):
    """生成明信片"""
    try:
        # 参数校验
        if not name or len(name) > 20:
            raise HTTPException(status_code=400, detail="名字长度需在1-20字之间")
        if gender not in ["male", "female", "other"]:
            raise HTTPException(status_code=400, detail="请选择有效的性别")
        if not hobby or len(hobby) > 50:
            raise HTTPException(status_code=400, detail="请填写爱好（不超过50字）")
        if not wish or len(wish) > 100:
            raise HTTPException(status_code=400, detail="请填写开学祝语（不超过100字）")
        
        ctx = new_context(method="generate_postcard")
        
        logger.info(f"Generating postcard for {name}, photo: {'yes' if photo_url else 'no'}")
        
        file_key, download_url = create_postcard(
            name=name,
            gender=gender,
            hobby=hobby,
            wish=wish,
            reference_image_url=photo_url if photo_url else None,
            ctx=ctx
        )
        
        return JSONResponse({
            "success": True,
            "file_key": file_key,
            "download_url": download_url,
            "message": "明信片生成成功！"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Postcard generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "华师明信片制作智能体运行中"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
