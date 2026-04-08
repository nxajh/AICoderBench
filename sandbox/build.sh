#!/bin/bash
# 构建 AICoderBench 评测沙箱镜像
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker build -t aicoderbench/evaluator:latest "$SCRIPT_DIR"
echo "Docker image built: aicoderbench/evaluator:latest"
