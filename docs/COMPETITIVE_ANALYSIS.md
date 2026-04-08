# 竞品分析与借鉴

## 1. LLMCodeArena (codearenaeval.github.io / llmcodearena.com)

**定位**：大模型 agentic coding 能力评测
- 1120 道题，Python/C++/JavaScript
- 评估模型自主规划、写代码、调试、迭代的完整流程
- 多文件仓库、真实开源项目任务
- 社区投票（人类偏好）
- 评分：CodeArena-Score = 正确性 + 效率 + 自主性
- 完整日志，每次交互可回溯

**与我们的区别**：
- 他们偏"工程任务"（修bug、补功能），我们偏"从零设计实现"
- 他们关注 agentic 行为（多轮迭代），我们关注单次生成质量
- 他们无并发安全/内存安全检测，我们有 TSan/ASan 全链路

## 2. AICoderEval (arxiv.org/abs/2406.04712)

**定位**：大模型在 AI 领域代码生成能力评测
- 来源：AutoAgents.ai + 复旦 + 多伦多大学，2024年6月
- 基于 HuggingFace/PyTorch/TensorFlow 库的真实 AI 任务
- 约 9000 个代码文件经人工筛选
- 评分指标：pass@1（一次生成通过率）

**可借鉴：**
- **每题3类测试用例**：正常执行测试、边界/异常处理测试、输出正确性验证测试
- **数据集开源到 HuggingFace**，方便社区使用和引用
- **用 GPT-4 辅助生成初始数据**，再人工审核筛选

**与我们的区别**：
- 领域：AI/ML 专用库调用 vs 通用软件工程
- 语言：Python only vs C/Rust → 多语言
- 评测维度：仅功能正确性 vs 五维度全自动
- 形态：静态数据集 vs 开放评测平台

## 3. SWE-bench (swe-bench.com)

**定位**：评测模型修复真实 GitHub issue 的能力
- 基于 Python 开源项目的真实 PR
- 给定仓库代码 + issue 描述 → 模型生成 patch
- 自动运行仓库测试套件验证

**可借鉴：**
- **真实工程场景**比人造题目更有说服力
- **patch-based 验证**方法可参考
- 后续可加入"修bug"类题目

## 4. CodeScaleBench (github.com/sourcegraph/CodeScaleBench)

**定位**：大规模代码库上的 AI coding agent 评测
- 370 道题，分 SDLC（150题，覆盖开发全生命周期）和 Org（220题，跨仓库协作）
- Patch-based 验证 + artifact 验证

**可借鉴：**
- 按开发阶段分类题目的思路
- 多仓库、多文件的复杂场景

## 5. DeepCodeBench (Qodo/qodo-ai)

**定位**：真实代码库理解 + QA benchmark
- 关注代码理解而非仅生成
- 评测维度更贴近实际工程需求

## 6. LiveBench (github.com/livebench/livebench)

**定位**：防污染的 LLM 综合评测
- 23项任务，每6个月更新题目
- 涵盖编码、推理、数学、语言等
- 使用近期数据避免训练集污染

**可借鉴：**
- **定期更新题库**防止模型针对性训练
- 多维度综合评测的思路

---

## 综合借鉴清单

### 题目设计
- [ ] 每题3类测试用例（正常/边界/正确性）— 来自 AICoderEval
- [ ] 按开发阶段/场景分类 — 来自 CodeScaleBench
- [ ] 定期更新题库 — 来自 LiveBench

### 评测方法
- [ ] patch-based 验证（后续扩展"修bug"题型）— 来自 SWE-bench
- [ ] 完整日志记录，每次评测可回溯 — 来自 CodeArena
- [ ] 执行环境容器化保证可复现 — 行业标准

### 平台运营
- [ ] 数据集开源到 HuggingFace — 来自 AICoderEval
- [ ] 社区参与（用户出题/投票）— 来自 CodeArena
- [ ] 定期发布评测报告 — 行业标准

### AICoderBench 差异化优势（竞品没有的）
- 多维度自动评测：功能 + 并发安全 + 内存安全 + 代码质量 + 性能
- Docker 沙箱 + TSan/ASan/cppcheck 全链路
- 用户可自定义出题
- 用户可自带模型评测
- 专注国产模型（同时支持国际模型对比）
