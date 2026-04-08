"""
AICoderBench 配置
"""
import os
from pathlib import Path

# 路径
_config_file = Path(__file__).resolve()
BASE_DIR = _config_file.parent.parent  # /app (backend 目录)
PROBLEMS_DIR = BASE_DIR / "problems"
RESULTS_DIR = BASE_DIR / "results"
SANDBOX_DIR = BASE_DIR / "sandbox"

# 数据库
DATA_DIR = BASE_DIR / "data"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'aicoderbench.db'}")

# Docker 沙箱
DOCKER_IMAGE = "aicoderbench-eval"
DOCKER_MEMORY = "128m"
DOCKER_CPUS = 1
DOCKER_TIMEOUT = 120  # 秒
SANDBOX_CONCURRENCY = int(os.getenv("SANDBOX_CONCURRENCY", "1"))

# 模型调用
MODEL_TIMEOUT = 60  # 秒
MODEL_TEMPERATURE = 0
MODEL_MAX_TOKENS = 8192
MAX_RETRIES = 3

# 编译
COMPILE_TIMEOUT = 30  # 秒
TEST_TIMEOUT = 30
TSAN_TEST_TIMEOUT = 60
