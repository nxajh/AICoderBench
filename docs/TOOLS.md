# 评测工具调研

## 一、并发安全检测

| 工具 | 语言 | 检测能力 | 用途 |
|------|------|----------|------|
| **TSan (ThreadSanitizer)** | C/C++ | 数据竞争、锁顺序反转、死锁 | 核心工具，gcc/clang 内置 `-fsanitize=thread` |
| **Helgrind** | C/C++ | 数据竞争、锁顺序、POSIX 语义错误 | Valgrind 插件，比 TSan 更慢但场景更全 |
| **DRD** | C/C++ | 数据竞争、锁违例 | Valgrind 插件，比 Helgrind 轻量 |

**评测方案**：TSan 为主（速度快，CI 友好），Helgrind 为辅（疑难场景交叉验证）

## 二、内存安全检测

| 工具 | 语言 | 检测能力 | 用途 |
|------|------|----------|------|
| **ASan (AddressSanitizer)** | C/C++ | 越界、use-after-free、double-free、泄漏 | 核心工具，gcc/clang 内置 `-fsanitize=address` |
| **MSan (MemorySanitizer)** | C/C++ | 未初始化内存读取 | 补充检测，clang 专有 |
| **UBSan (UndefinedBehaviorSanitizer)** | C/C++ | 未定义行为（溢出、空指针解引用等） | 补充检测 |
| **Valgrind (Memcheck)** | C/C++ | 内存泄漏、越界、未初始化读取 | 经典工具，全面但慢 |
| **LeakSanitizer** | C/C++ | 内存泄漏 | ASan 内置，或独立使用 |

**评测方案**：ASan + UBSan 组合（编译期加入，速度快），Valgrind 作为交叉验证

## 三、代码质量 / 静态分析

| 工具 | 语言 | 检测能力 | 输出 |
|------|------|----------|------|
| **cppcheck** | C/C++ | bug、未定义行为、风格问题、MISRA 违规 | 问题列表 + 严重等级 |
| **clang-tidy** | C/C++ | bug、风格、性能、可读性、现代C++实践 | 问题列表 + auto-fix |
| **flawfinder** | C | 安全漏洞扫描 | CVE 相关风险项 |
| **splint** | C | 类型安全、内存管理、接口契约 | 问题列表 |

**度量指标（可自动化）：**
- 圈复杂度（Cyclomatic Complexity）
- 认知复杂度（Cognitive Complexity）
- 代码行数 / 函数行数
- 注释率
- 重复代码率

**工具：**
- **lizard** — 多语言圈复杂度计算，命令行友好，可输出 JSON
- **Metrix++** — 代码度量集合工具
- **cloc** — 代码行数统计

**评测方案**：cppcheck（bug检测）+ lizard（复杂度度量）+ cloc（行数统计）

## 四、性能评估

| 工具 | 用途 | 精度 |
|------|------|------|
| **perf** | Linux 性能分析，CPU 采样、缓存miss、分支预测 | 高 |
| **Callgrind** | Valgrind 插件，指令级计数 | 极高（但慢） |
| **Cachegrind** | Valgrind 插件，缓存模拟 | 极高（但慢） |
| **hyperfine** | 命令行 benchmark 工具，统计多次运行时间 | 中 |
| **time（精度版）** | 简单计时，gettimeofday/clock_gettime | 低 |

**评测方案**：编写统一的 benchmark 测试用例，用 hyperfine 或 perf stat 跑固定次数取均值

## 五、Rust 专用工具（后续扩展用）

| 工具 | 用途 |
|------|------|
| **cargo clippy** | Rust 官方 linter，800+ 规则 |
| **rust-code-analysis** | 圈复杂度、认知复杂度、Halstead 度量等 |
| **MIRI** | Rust 未定义行为检测（特别是 unsafe 代码） |
| **cargo-audit** | 依赖安全审计 |
| **Criterion.rs** | 性能基准测试 |
| **cargo-flamegraph** | 火焰图生成 |

## 六、综合评测方案（C 语言首轮）

### 自动化流水线（每份代码依次跑）

```
Step 1: 静态分析
  ├── cppcheck --enable=all --suppress=missingInclude  → bug 数量
  ├── lizard                    → 圈复杂度
  └── cloc                      → 代码行数

Step 2: 编译
  ├── gcc -Wall -Wextra -O2                    → 编译通过/失败 + warning 数
  ├── gcc -fsanitize=thread                    → TSan 版本
  └── gcc -fsanitize=address,undefined         → ASan+UBSan 版本

Step 3: 功能测试
  ├── 运行普通版本    → 通过/失败/超时
  ├── 运行 TSan 版本  → 是否有数据竞争报告
  └── 运行 ASan 版本  → 是否有内存错误报告

Step 4: 性能测试（可选，视题目而定）
  └── perf stat / hyperfine  → 执行时间、吞吐量
```

### 自动评分 + 人工评分结合

| 维度 | 自动/人工 | 工具 |
|------|-----------|------|
| 编译通过 (10分) | 自动 | gcc |
| 功能正确 (20分) | 自动 | test.c |
| 并发安全 (25分) | 自动+人工 | TSan + 代码审查 |
| 代码质量 (20分) | 自动+人工 | cppcheck + lizard + 代码审查 |
| 内存管理 (15分) | 自动+人工 | ASan + 代码审查 |
| 性能设计 (10分) | 人工 | perf 数据 + 架构审查 |

### 自动化输出格式

```json
{
  "model": "glm-5",
  "problem": "rate_limiter",
  "auto_scores": {
    "compile": {"pass": true, "warnings": 2, "score": 9},
    "tests": {"pass": 5, "fail": 0, "score": 20},
    "tsan": {"issues": 0, "score": 20},
    "asan": {"issues": 0, "score": 12},
    "cppcheck": {"errors": 0, "warnings": 3, "style": 5},
    "complexity": {"avg_cyclomatic": 4.2, "max_cyclomatic": 8},
    "loc": {"total": 180, "comment_ratio": 0.12}
  },
  "manual_scores": {
    "lock_design": null,
    "code_readability": null,
    "boundary_handling": null,
    "performance_arch": null
  }
}
```
