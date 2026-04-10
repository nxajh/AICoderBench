"""
AICoderBench 配置
"""
import os
from pathlib import Path

# 路径
_config_file = Path(__file__).resolve()
BASE_DIR = _config_file.parent.parent  # /app (backend 目录)
RESULTS_DIR = BASE_DIR / "results"
SANDBOX_DIR = BASE_DIR / "sandbox"

# 题目目录：
# - Docker 部署：docker-compose 将项目根 problems/ 挂载到 /app/problems（即 BASE_DIR/problems）
# - 本地开发：backend/ 内无 problems/ 子目录，自动回退到项目根的 problems/
# - 环境变量 PROBLEMS_DIR 可覆盖（优先级最高）
_env_problems = os.getenv("PROBLEMS_DIR", "")
if _env_problems:
    PROBLEMS_DIR = Path(_env_problems)
else:
    _default_problems = BASE_DIR / "problems"
    PROBLEMS_DIR = _default_problems if _default_problems.is_dir() else BASE_DIR.parent / "problems"

# 数据库
DATA_DIR = BASE_DIR / "data"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'aicoderbench.db'}")

# Docker 沙箱
DOCKER_IMAGE = "aicoderbench-eval"
DOCKER_MEMORY = "128m"
DOCKER_MEMORY_MB = 128       # 与 DOCKER_MEMORY 保持一致，供并发计算使用
DOCKER_CPUS = 1
DOCKER_TIMEOUT = 300  # 秒（含 valgrind memcheck + helgrind）


def _auto_sandbox_concurrency() -> int:
    """根据机器 CPU 和可用内存自动推算最优沙箱并发数。

    策略：
    - CPU 维度：每 2 核分配 1 个容器。
      Valgrind 等工具是 CPU 密集型单线程任务，满载并行会互相抢占，
      取半数可在并发与吞吐之间取得平衡。
    - 内存维度：(可用内存 × 0.80) / 每容器内存，
      预留 20% 给 OS、后端进程和 Linux page cache。
    - 取两者最小值，下限为 1。
    """
    import multiprocessing

    # CPU 维度
    try:
        cpu_count = multiprocessing.cpu_count()
    except Exception:
        cpu_count = 2
    by_cpu = max(1, cpu_count // 2)

    # 内存维度（/proc/meminfo，仅 Linux 可用）
    by_mem = by_cpu  # 非 Linux 时退化为 CPU 维度
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    available_mb = int(line.split()[1]) / 1024  # kB → MB
                    usable_mb = available_mb * 0.80
                    by_mem = max(1, int(usable_mb / DOCKER_MEMORY_MB))
                    break
    except (OSError, ValueError):
        pass  # 忽略：非 Linux 或 /proc 不可读

    return min(by_cpu, by_mem)


# SANDBOX_CONCURRENCY：
#   - 环境变量显式设置（值 > 0）→ 使用指定值，方便在 compose/k8s 中手动调优
#   - 未设置或设为 0 → 运行时自动根据机器配置推算
_concurrency_env = int(os.getenv("SANDBOX_CONCURRENCY", "0"))
SANDBOX_CONCURRENCY = _concurrency_env if _concurrency_env > 0 else _auto_sandbox_concurrency()

# 模型调用
MODEL_TIMEOUT = 60  # 秒
MODEL_TEMPERATURE = 0
MODEL_MAX_TOKENS = 8192
AGENT_MAX_TOKENS = 131072  # agent 轮次生成上限（含 thinking/reasoning）
MAX_RETRIES = 3

# 编译
COMPILE_TIMEOUT = 30  # 秒
TEST_TIMEOUT = 30
TSAN_TEST_TIMEOUT = 60
