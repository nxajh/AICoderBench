# AICoderBench 设计决策记录

所有决策确认后记录于此，开发以此为依据。

## 项目概述

- **名称**：AICoderBench
- **定位**：面向软件工程的大模型编码能力自动评测平台，评估结果用于 LLM 辅助编码选型
- **两个使用场景**：1) 平台提供模型，用户出题  2) 用户指定/提供模型，跑题库

## 技术栈

- 前端：Next.js + Tailwind + shadcn/ui，部署 Vercel
- 后端：Python + FastAPI
- 数据库：SQLite → PostgreSQL
- 沙箱：Docker，并发池可配置（当前 concurrency=1）
- 部署：VPS（Oracle Cloud ARM, 1核2线程/680MB）+ Vercel

## 题目设计

- MVP 单文件（一个 .h 接口 + 一个 .c 实现）
- MVP 只做 C 语言，Rust 作为 v0.2 扩展
- difficulty 由出题者定（简单/中等/困难）
- 每题3类测试用例：正常执行、边界/异常处理、输出正确性验证
- 题目元数据存 problem.json，含评分权重配置

## 模型调用

- **MVP 模型**：GLM、Kimi、MiniMax（已有 API key）
- **代码获取**：tool calling（write_file）为主，文本+正则提取兜底
- temperature = 0（确定性，可复现）
- max_tokens = 8192
- MVP 每题生成1次，数据结构预留 attempt 字段
- **多模型并行调用**（网络IO不占本地资源）

## 评测流水线

### Docker 沙箱
- 镜像预装：gcc/clang + TSan/ASan + cppcheck + lizard + cloc + hyperfine
- 安全限制：128MB内存 / 无网络 / 只写 /sandbox / 超时强制终止
- 并发数可配置

### 三阶段评测
- Stage 1：编译（普通版 + TSan版 + ASan版）
- Stage 2：运行测试（普通版跑功能，TSan/ASan版跑并发）
- Stage 3：静态分析（cppcheck + lizard + cloc）

### 超时策略
- 模型 API 调用：60秒
- 编译：30秒
- 普通测试：30秒
- TSan/ASan 测试：60秒

### 结果输出
- 评测脚本输出结构化 JSON，后端直接读取入库
- 不做日志解析

## 评分规则

### 六维度100分（可按题目配置权重）
| 维度 | 默认分值 | 评分方式 |
|------|----------|----------|
| 编译 | 10 | 通过/失败 + warning扣分 |
| 功能正确 | 25 | 测试用例通过比例 |
| 并发安全 | 25 | TSan issue数 |
| 内存安全 | 15 | ASan + UBSan issue数 |
| 代码质量 | 15 | cppcheck + 圈复杂度 + 函数行数 |
| 性能 | 10 | MVP给满分，v0.2引入参考实现 |

### 扣分规则
- 编译不过：该题0分
- 编译 warning：每个扣1分（上限5分）
- TSan issue：每个扣5分
- ASan issue：每个扣3分
- cppcheck error：每个扣3分，warning每个扣1分
- 圈复杂度 > 15 的函数：每个扣1分
- 每个维度最低0分，不设负分
- 性能测试：problem.json 中 has_benchmark 标记，非所有题都跑

## 数据结构

- submission 表含 `attempt` 和 `parent_submission_id`，预留多轮迭代
- 保存模型原始输出（完整对话/tool call记录）
- 历史评测数据永久保留
- 记录模型版本、prompt版本、评分规则版本，方便追溯
- 支持同模型不同版本对比（如 GLM-4 vs GLM-5）

## 平台功能

### MVP（匿名，无用户系统）
- 管理员配置模型 API key（环境变量）
- 一键跑评测：选模型 + 选题目 → 并行生成 → 排队沙箱评测 → 出结果
- 排行榜：按模型总分 + 按题目对比
- 静态 JSON 生成（非实时）

### v0.2+
- 用户注册/登录
- 用户出题（需审核）
- 用户自带模型（API key 安全方案待定）
- 多语言（Rust）
- 多轮迭代评测（给报错让模型自己修）

## 错误处理

- 429 限流：指数退避（2s → 4s → 8s），最多3次，超过标记失败
- API 超时：60秒，重试1次后标记失败
- 代码编译失败：该题0分，记录编译错误信息
- 沙箱异常：容器超时强制终止，标记失败
