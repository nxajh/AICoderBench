# AICoderBench

AI编码能力自动评测平台——评测国产大模型在系统编程（C语言）上的真实能力。

## 架构

- **后端**: FastAPI + SQLite + Docker沙箱评测
- **前端**: Next.js 14 + Tailwind CSS（暗色主题）
- **评测流水线**: 编译 → 功能测试 → TSan(并发) → ASan(内存) → 静态分析 → 自动评分

## 题库（10道）

| # | 题目 | 难度 | 考点 |
|---|------|------|------|
| 1 | 高并发滑动窗口限流器 | medium | mutex, hash-table |
| 2 | Lock-Free SPSC Ring Buffer | easy | atomic, lock-free |
| 3 | 递归下降表达式解释器 | medium | parser, string |
| 4 | 线程安全LRU缓存 | medium | mutex, linked-list |
| 5 | MPMC阻塞队列 | hard | condition-variable |
| 6 | 固定块内存池 | easy | embedded free-list |
| 7 | Copy-on-Write容器 | hard | atomic, refcount |
| 8 | 分段锁并发哈希表 | medium | segment-lock |
| 9 | 异步日志系统 | medium | producer-consumer |
| 10 | 事件循环(定时器) | hard | min-heap, callback |

## 评分维度（满分100）

| 维度 | 权重 | 说明 |
|------|------|------|
| 编译 | 10 | 干净编译，无warning |
| 功能测试 | 25 | 测试用例通过率 |
| 并发安全 | 25 | TSan检测无数据竞争 |
| 内存安全 | 15 | ASan无内存错误 |
| 代码质量 | 15 | 静态分析 + 圈复杂度 |
| 性能 | 10 | 执行效率 |

## 快速开始

```bash
# 1. 启动后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. 启动前端
cd frontend
npm install && npm run dev

# 3. 运行评测
curl -X POST http://localhost:8000/api/rounds/sync \
  -H 'Content-Type: application/json' \
  -d '{"name":"test","problem_ids":["06-memory-pool"],"model_ids":["minimax"]}'
```

## Docker部署

```bash
docker-compose up --build
```

## 环境变量

| 变量 | 说明 |
|------|------|
| MINIMAX_API_KEY | MiniMax API密钥 |
| GLM_API_KEY | 智谱API密钥 |
| KIMI_API_KEY | Moonshot API密钥 |
| NEXT_PUBLIC_API_URL | 前端API地址 |

## API

- `GET /api/problems` - 题库列表
- `GET /api/models` - 可用模型
- `POST /api/rounds` - 异步创建评测轮次
- `POST /api/rounds/sync` - 同步评测（阻塞等结果）
- `GET /api/rounds` - 轮次列表
- `GET /api/rounds/{id}` - 轮次详情 + 排行榜
- `GET /api/leaderboard/{round_id}` - 排行榜
- `GET /api/submissions/{round_id}/{problem_id}/{model_id}` - 提交详情

## License

MIT
