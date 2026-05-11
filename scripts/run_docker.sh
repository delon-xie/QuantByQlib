#!/bin/bash
# scripts/run_docker.sh

set -e

# ✅ 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ✅ 项目根目录
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

IMAGE_NAME="local_qlib:latest"

# ✅ 加载 .env
set -o allexport
source "$PROJECT_ROOT/.env"
set +o allexport

# 创建数据目录
mkdir -p ~/.qlib/qlib_data
mkdir -p ./logs

echo "SPROJECT_ROOT=$PROJECT_ROOT"
echo "$HOME/.qlib"

# 运行容器
docker run -it --rm \
    --name qlib_rd_agent \
    --network host \
    -v "$SCRIPT_DIR/run_factor_discovery.py":/workspace/run_factor_discovery.py \
    -v "$PROJECT_ROOT/core":/workspace/core \
    -v "$HOME/.qlib/qlib_data":/root/.qlib/qlib_data \
    -v "$PROJECT_ROOT/logs":/workspace/logs \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
    -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
    -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY}" \
    -e GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
    -e QLIB_DATA_URI="/root/.qlib/qlib_data/cn_data" \
    ${IMAGE_NAME} \
    # python /workspace/run_factor_discovery.py --provider deepseek --reg cn