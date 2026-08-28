#!/bin/bash
# 华师明信片本地启动脚本

set -e

echo "🎓 华南师范大学明信片制作智能体启动中..."

# 检查uv是否安装
if ! command -v uv &> /dev/null; then
    echo "❌ 请先安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 进入脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📦 检查并安装依赖..."
uv sync

echo "🔧 加载环境变量..."
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ 已加载 .env 配置"
else
    echo "⚠️  未找到 .env 文件，使用平台默认环境变量"
fi

export COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-.}"
export PYTHONPATH=src:$PYTHONPATH

PORT="${1:-9000}"
echo "🚀 启动服务，端口: $PORT"
echo "📍 访问地址: http://localhost:$PORT"
echo ""

uv run uvicorn src.main:app --host 0.0.0.0 --port "$PORT"
