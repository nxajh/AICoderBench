# AICoderBench 系统设计文档

## 项目名称
**AICoderBench** — AI编码能力评测平台

## 定位
面向软件工程的大模型编码能力自动评测平台。评估结果用于 LLM 辅助编码的选型参考。多维度自动评分，零人工介入。

---

## 技术栈

| 层 | 技术选型 | 说明 |
|----|----------|------|
| 前端 | Next.js + Tailwind + shadcn/ui | 部署到 Vercel（免费） |
| 后端 | Python + FastAPI | 异步、OpenAPI 文档自动生成 |
| 数据库 | SQLite → PostgreSQL | MVP 用 SQLite，后续迁移 |
| 沙箱 | Docker | 隔离执行模型生成的代码 |
| 部署 | VPS 全栈 → 前后端分离 | MVP 全栈，演进分离 |

## 系统架构

```
┌─────────────┐     ┌──────────────────────────────┐
│   Next.js   │────▶│         FastAPI 后端          │
│   (前端)    │     │                              │
└─────────────┘     │  ┌──────────┐  ┌───────────┐ │
                    │  │ 题库管理  │  │ 模型接入层 │ │
                    │  └──────────┘  └───────────┘ │
                    │  ┌──────────┐  ┌───────────┐ │
                    │  │ 调度引擎  │  │ 评分引擎  │ │
                    │  └─────┬────┘  └───────────┘ │
                    │        │                      │
                    │        ▼                      │
                    │  ┌──────────────────────────┐ │
                    │  │    Docker 沙箱池          │ │
                    │  │  ┌────┐ ┌────┐ ┌────┐    │ │
                    │  │  │ C1 │ │ C2 │ │ C3 │    │ │
                    │  │  └────┘ └────┘ └────┘    │ │
                    │  └──────────────────────────┘ │
                    │        │                      │
                    │        ▼                      │
                    │  ┌──────────────────────────┐ │
                    │  │   评测工具链              │ │
                    │  │  gcc TSan ASan cppcheck   │ │
                    │  │  lizard cloc hyperfine    │ │
                    │  └──────────────────────────┘ │
                    └──────────────────────────────┘
```

---

## 核心模块设计

### 1. 题库管理（Problems）

每道题的目录结构：
```
problems/
└── 01-rate-limiter/
    ├── problem.json       # 题目元数据 + 接口定义
    ├── problem.md         # 题目描述（给人 + 给模型看）
    ├── solution.h         # 接口头文件
    ├── test_basic.c       # 基础测试
    ├── test_concurrent.c  # 并发测试
    └── benchmark.c        # 性能测试
```

problem.json 示例：
```json
{
  "id": "rate-limiter",
  "title": "高并发滑动窗口限流器",
  "difficulty": "medium",
  "tags": ["concurrency", "lock", "hash-table"],
  "language": "c",
  "compile_flags": "-lpthread",
  "timeout_seconds": 10,
  "scoring": {
    "compile": 10,
    "tests": 25,
    "concurrency": 25,
    "memory": 15,
    "quality": 15,
    "performance": 10
  }
}
```

### 2. 模型接入层（Models）

统一接口，方便扩展：
```python
class ModelProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str: ...

class GLMProvider(ModelProvider): ...
class KimiProvider(ModelProvider): ...
class MiniMaxProvider(ModelProvider): ...
class DeepSeekProvider(ModelProvider): ...  # 后续
class QwenProvider(ModelProvider): ...      # 后续
class ClaudeProvider(ModelProvider): ...    # 参考基准，后续
```

MVP 支持：GLM、Kimi、MiniMax（已有 API key）

**代码生成策略：优先 tool calling，兜底文本解析**

方案1（主）：提供 `write_file(path, content)` 工具，支持 function calling 的模型通过 tool call 写入文件
方案2（兜底）：不支持 tool calling 的模型走文本生成 + 正则提取 ```c ... ``` 代码块

Prompt 模板统一管理：
```python
PROMPT_TEMPLATE = """
请用 C 语言实现以下功能。

## 接口定义
{interface}

## 要求
{requirements}

## 约束
- 代码完整可编译，包含所有必要的 #include
- 通过 TSan 和 ASan 检测
- 正确处理边界情况和错误
- 不使用外部库

请直接输出代码，不要解释。
"""
```

**超时策略：**
- 模型 API 调用：60秒
- 编译：30秒
- 普通测试运行：30秒
- TSan/ASan 测试运行：60秒

### 3. 调度引擎（Scheduler）

核心流程：
```
1. 从题库加载题目
2. 为每道题 × 每个模型生成任务
3. 调用模型 API 获取代码
4. 提交到 Docker 沙箱执行评测流水线
5. 收集结果，存入数据库
```

任务状态机：
```
PENDING → GENERATING → COMPILED → TESTING → SCORING → DONE
                                        ↘ FAILED
```

并发控制：
- **模型 API 调用**：多模型并行（网络 IO，不占本地计算资源）
- **Docker 沙箱**：顺序执行（VPS 内存限制，一次只跑一个容器）
- 整体流程：并行生成代码 → 排队评测 → 并行收集结果
- API 调用控制速率（避免 429）

### 4. Docker 沙箱（Sandbox）

Dockerfile：
```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y \
    gcc g++ clang \
    cppcheck lizard cloc \
    valgrind \
    hyperfine \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /sandbox
```

安全限制：
- `--cpus=1`
- `--memory=256m`
- `--network=none`
- `--read-only` + tmpfs `/tmp`
- `--pids-limit=64`
- 超时强制终止

### 5. 评测引擎（Evaluator）

评测流水线（沙箱内执行）：

```bash
#!/bin/bash
set -e

CODE=$1
RESULT_FILE=$2

# Step 1: 静态分析
cppcheck --enable=all --suppress=missingInclude \
    --xml 2> cppcheck.xml 2>&1 || true
lizard --json solution.c > lizard.json || true
cloc --json solution.c > cloc.json || true

# Step 2: 编译
WARNINGS=0
gcc -Wall -Wextra -O2 -o solution_normal solution.c -lpthread -lm 2>&1 | tee compile.log || echo "COMPILE_FAIL"
[ -f solution_normal ] && echo "COMPILE_OK"

# Step 3: TSan 编译 + 运行
gcc -fsanitize=thread -O1 -o solution_tsan solution.c -lpthread -lm 2>&1 || true
timeout 30 ./solution_tsan 2>&1 | tee tsan.log || true

# Step 4: ASan + UBSan 编译 + 运行
gcc -fsanitize=address,undefined -O1 -o solution_asan solution.c -lpthread -lm 2>&1 || true
timeout 30 ./solution_asan 2>&1 | tee asan.log || true

# Step 5: 功能测试
timeout 30 ./solution_normal 2>&1 | tee test.log || true

# Step 6: 性能测试（可选）
hyperfine --runs=3 './solution_normal' 2>&1 | tee perf.log || true

# 汇总结果为 JSON
python3 /evaluator/score.py > $RESULT_FILE
```

### 6. 评分引擎（Scorer）

自动评分规则：

```python
def score(result: EvalResult) -> Score:
    s = Score()

    # 编译 (10分)
    if result.compile_success:
        s.compile = 10 - min(result.warnings, 5)  # 每个warning扣1分，最多扣5分

    # 功能正确 (25分)
    s.tests = 25 * result.tests_passed / result.tests_total

    # 并发安全 (25分)
    if result.tsan_issues == 0:
        s.concurrency = 25
    else:
        s.concurrency = max(0, 25 - result.tsan_issues * 5)

    # 内存安全 (15分)
    if result.asan_issues == 0 and result.ubsan_issues == 0:
        s.memory = 15
    else:
        s.memory = max(0, 15 - result.asan_issues * 3 - result.ubsan_issues * 2)

    # 代码质量 (15分)
    # 基于cppcheck问题数 + 圈复杂度 + 函数行数
    quality_penalty = result.cppcheck_errors * 3 + result.cppcheck_warnings
    complexity_penalty = max(0, (result.max_cyclomatic - 10)) * 1
    s.quality = max(0, 15 - quality_penalty - complexity_penalty)

    # 性能 (10分)
    # 基于执行时间，与最优实现对比
    s.performance = 10 * result.best_time / result.this_time

    return s
```

### 7. 数据模型（Database）

```sql
-- 题目
CREATE TABLE problems (
    id TEXT PRIMARY KEY,
    title TEXT,
    difficulty TEXT,
    language TEXT DEFAULT 'c',
    scoring_config JSON
);

-- 模型
CREATE TABLE models (
    id TEXT PRIMARY KEY,
    name TEXT,
    provider TEXT,
    version TEXT
);

-- 评测轮次
CREATE TABLE rounds (
    id INTEGER PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending'
);

-- 评测结果
CREATE TABLE submissions (
    id INTEGER PRIMARY KEY,
    round_id INTEGER REFERENCES rounds(id),
    problem_id TEXT REFERENCES problems(id),
    model_id TEXT REFERENCES models(id),
    code TEXT,
    status TEXT,  -- pending/compiling/testing/scoring/done/failed
    scores JSON,  -- 各维度分数
    eval_output JSON,  -- 原始评测输出
    total_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(round_id, problem_id, model_id)
);
```

---

## API 设计

```
# 题目
GET    /api/problems                    # 题目列表
GET    /api/problems/{id}               # 题目详情

# 模型
GET    /api/models                      # 模型列表

# 评测
POST   /api/rounds                      # 创建评测轮次
GET    /api/rounds                      # 轮次列表
GET    /api/rounds/{id}                 # 轮次详情
POST   /api/rounds/{id}/run             # 启动评测
GET    /api/rounds/{id}/status          # 评测进度

# 结果
GET    /api/results/leaderboard         # 总排行
GET    /api/results/{round_id}          # 某轮次结果
GET    /api/results/{round_id}/{problem_id}/{model_id}  # 单题详情

# 代码对比
GET    /api/compare/{round_id}/{problem_id}?models=a,b,c  # 多模型代码对比
```

---

## 前端页面

```
/                           # 首页：最新排行 + 简介
/leaderboard                # 总排行榜（表格 + 雷达图）
/rounds                     # 评测轮次列表
/rounds/{id}                # 某轮次详情
/problems                   # 题库列表
/problems/{id}              # 题目详情 + 各模型代码对比
/compare/{round}/{problem}  # 并排代码对比页
```

---

## 项目目录结构

```
llm-oj/
├── frontend/                # Next.js
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── backend/                 # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── models/          # 数据模型
│   │   ├── providers/       # 模型 API 接入
│   │   ├── evaluator/       # 评测引擎
│   │   ├── scheduler/       # 调度引擎
│   │   └── api/             # API 路由
│   ├── requirements.txt
│   └── Dockerfile
├── sandbox/                 # Docker 沙箱
│   ├── Dockerfile
│   └── evaluator/
│       ├── run_eval.sh
│       └── score.py
├── problems/                # 题库
│   ├── 01-rate-limiter/
│   ├── 02-ring-buffer/
│   └── ...
├── docker-compose.yml
└── README.md
```

---

## 开发里程碑

### MVP（v0.1）— 单机可运行
- 后端：题库加载 + 模型调用 + Docker 评测 + 评分
- 前端：排行榜 + 代码对比页
- 题目：3道（已有的限流器、环形缓冲区、解释器）
- 模型：3家（GLM、Kimi、DeepSeek）

### v0.2 — 功能完善
- 题目扩展到 10 道
- 模型扩展到 6 家
- 评测轮次管理
- 自动生成评测报告（Markdown）

### v0.3 — 开放平台
- 用户注册/登录
- 自定义题目提交
- 模型 API key 管理
- 评测历史和趋势图

### v1.0 — 正式上线
- 域名 + 正式部署
- CI/CD 自动化评测
- 社区功能（评论、讨论）
- Rust 题目支持
