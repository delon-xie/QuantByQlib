#!/bin/bash
# scripts/build_docker_deepseek.sh

set -e  # 遇到错误退出

IMAGE_NAME="local_qlib"
TAG="latest"
FULL_NAME="${IMAGE_NAME}:${TAG}"

echo "Building Qlib RD-Agent Docker image: ${FULL_NAME}"

# 构建镜像
docker build \
    --network=host \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    --no-cache \
    -t ${FULL_NAME} \
    -f Dockerfile \
    .

echo "Build complete: ${FULL_NAME}"
echo "To run: docker run -it --rm ${FULL_NAME}"