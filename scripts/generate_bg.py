import sys
import os
sys.path.insert(0, os.path.join(os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"), "src"))

from tools.postcard_generator import generate_background_image, BACKGROUND_PATH
from coze_coding_utils.runtime_ctx.context import new_context

ctx = new_context(method="init_bg")
print("Generating background image...")
bg = generate_background_image(ctx)
bg.convert("RGB").save(BACKGROUND_PATH, "PNG", quality=95)
print(f"Background saved to: {BACKGROUND_PATH}")
