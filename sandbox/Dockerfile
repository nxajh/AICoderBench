FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    gcc g++ clang clang-tidy \
    python3 python3-pip \
    valgrind cloc \
    && rm -rf /var/lib/apt/lists/*

# Install lizard (圈复杂度分析)
RUN pip3 install lizard --break-system-packages

# 将评测脚本烤入镜像，避免运行时依赖宿主文件系统
COPY eval.sh /eval.sh
RUN chmod +x /eval.sh

WORKDIR /sandbox
