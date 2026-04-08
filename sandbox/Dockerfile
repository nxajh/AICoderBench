FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    gcc g++ clang clang-tidy \
    python3 python3-pip \
    valgrind \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install lizard and cloc via pip
RUN pip3 install lizard --break-system-packages

# Install cloc
RUN apt-get update && apt-get install -y cloc && rm -rf /var/lib/apt/lists/*

WORKDIR /sandbox
