"""
评测引擎 — 在 Docker 沙箱中执行评测流水线
"""
import json
import asyncio
import logging
import tempfile
import os
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EVAL_SCRIPT_PATH = Path(__file__).parent.parent.parent / "sandbox" / "eval.sh"


@dataclass
class EvalResult:
    """评测结果"""
    # 编译
    compile_success: bool = False
    compile_warnings: int = 0
    compile_errors: str = ""
    compile_tsan_success: bool = False
    compile_asan_success: bool = False

    # 功能测试
    tests_passed: int = 0
    tests_total: int = 0
    test_output: str = ""

    # TSan
    tsan_issues: int = 0
    tsan_output: str = ""

    # ASan + UBSan
    asan_issues: int = 0
    asan_output: str = ""

    # 静态分析（clang-tidy）
    clang_tidy_errors: int = 0
    clang_tidy_warnings: int = 0
    # 兼容旧数据（cppcheck 已停用，始终为 0）
    cppcheck_errors: int = 0
    cppcheck_warnings: int = 0
    cppcheck_output: str = ""
    # 危险 C API 调用数（gets/strcpy/strcat/sprintf/system）
    dangerous_apis: int = 0
    # 圈复杂度
    max_cyclomatic: int = 0
    avg_cyclomatic: float = 0.0
    # 函数最大行数（lizard）
    max_func_length: int = 0
    # 代码规模与注释
    total_loc: int = 0
    comment_ratio: float = 0.0
    # Valgrind 精确泄漏块数（直接 + 间接）
    valgrind_leaks: int = 0
    # Helgrind 线程问题数（仅并发题）
    helgrind_issues: int = 0

    # 评分
    score_compile: int = 0
    score_tests: int = 0
    score_safety: int = 0
    score_resource: int = 0
    score_quality: int = 0
    score_performance: int = 0
    score_total: int = 0

    # 元信息
    error: str = ""
    timed_out: bool = False
    exec_time_ms: int = 0


def compute_scores(result: EvalResult, scoring: dict, token_usage: dict = None,
                   concurrent: bool = True) -> EvalResult:
    """根据评测结果和评分配置计算分数

    Args:
        concurrent: 是否为并发题。影响 TSan 扣分（非并发题不检测 TSan）
    """
    weights = scoring or {
        "compile": 10, "tests": 25, "safety": 25,
        "resource": 15, "quality": 15, "performance": 10,
    }

    # 编译（编译失败 → 全题0分）
    if not result.compile_success:
        result.score_compile = 0
        result.score_total = 0
        return result

    result.score_compile = max(0, weights.get("compile", 10) - min(result.compile_warnings, 5))

    # 功能正确（按比例）
    tests_weight = weights.get("tests", 25)
    if result.tests_total > 0:
        result.score_tests = int(tests_weight * result.tests_passed / result.tests_total)

    # 安全性：
    #   ASan/UBSan     — 所有题目，每 issue 扣 3 分
    #   TSan           — 仅并发题，每 issue 扣 5 分
    #   Helgrind       — 仅并发题，每 issue 扣 2 分（对 TSan 的补充）
    #   危险 API 调用  — 所有题目，每处扣 3 分
    safety_weight = weights.get("safety", 25)
    safety_deduction = 0
    if result.compile_asan_success:
        safety_deduction += result.asan_issues * 3
    if concurrent and result.compile_tsan_success:
        safety_deduction += result.tsan_issues * 5
    if concurrent:
        safety_deduction += result.helgrind_issues * 2
    safety_deduction += result.dangerous_apis * 3
    result.score_safety = max(0, safety_weight - safety_deduction)

    # 代码质量：
    #   圈复杂度（max）按档位打底分
    #   圈复杂度（avg）超过 8 额外扣分
    #   clang-tidy 静态分析问题
    #   函数最大行数（> 80 行）扣分
    #   注释率（< 5%）扣分
    qual_weight = weights.get("quality", 15)
    max_cyclo = result.max_cyclomatic
    if max_cyclo <= 10:
        quality_score = qual_weight
    elif max_cyclo <= 15:
        quality_score = int(qual_weight * 0.9)
    elif max_cyclo <= 20:
        quality_score = int(qual_weight * 0.75)
    elif max_cyclo <= 30:
        quality_score = int(qual_weight * 0.55)
    elif max_cyclo <= 40:
        quality_score = int(qual_weight * 0.30)
    elif max_cyclo <= 50:
        quality_score = int(qual_weight * 0.10)
    else:
        quality_score = 0

    quality_penalty = result.clang_tidy_errors * 3 + result.clang_tidy_warnings

    # avg 圈复杂度超过 8 扣分（每超出 1 扣 0.5，最多扣 3 分）
    if result.avg_cyclomatic > 8:
        quality_penalty += min(3, int((result.avg_cyclomatic - 8) * 0.5))

    # 函数过长（> 80 行扣 1，> 120 行扣 2，> 200 行扣 3）
    if result.max_func_length > 200:
        quality_penalty += 3
    elif result.max_func_length > 120:
        quality_penalty += 2
    elif result.max_func_length > 80:
        quality_penalty += 1

    # 注释不足（LOC > 30 且注释率 < 5%，扣 2 分）
    if result.total_loc > 30 and result.comment_ratio < 0.05:
        quality_penalty += 2

    result.score_quality = max(0, quality_score - quality_penalty)

    # 资源管理：
    #   优先使用 Valgrind memcheck（更精确），否则回退到 ASan 泄漏计数
    resource_weight = weights.get("resource", 15)
    if result.valgrind_leaks > 0:
        # valgrind 已运行且检测到泄漏
        result.score_resource = max(0, resource_weight - result.valgrind_leaks * 3)
    elif result.compile_asan_success and result.asan_output:
        # 回退：从 ASan 输出统计直接/间接泄漏块（各自一行 "Direct/Indirect leak"）
        direct_leaks = len(re.findall(r'Direct leak', result.asan_output))
        indirect_leaks = len(re.findall(r'Indirect leak', result.asan_output))
        leak_count = direct_leaks + indirect_leaks
        result.score_resource = max(0, resource_weight - leak_count * 3)
    else:
        # 无泄漏检测数据则给满分
        result.score_resource = resource_weight

    # 性能：与 perf_baseline_ms 对比
    perf_weight = weights.get("performance", 10)
    perf_baseline_ms = weights.get("perf_baseline_ms", 0)
    if perf_baseline_ms <= 0 or result.exec_time_ms <= 0:
        # 基准未配置或无执行时间，给满分
        result.score_performance = perf_weight
    else:
        ratio = result.exec_time_ms / perf_baseline_ms
        if ratio <= 0.5:
            result.score_performance = perf_weight
        elif ratio <= 1.0:
            result.score_performance = int(perf_weight * 0.8)
        elif ratio <= 2.0:
            result.score_performance = int(perf_weight * 0.5)
        else:
            result.score_performance = 0

    # 总分
    result.score_total = (
        result.score_compile + result.score_tests + result.score_safety +
        result.score_resource + result.score_quality + result.score_performance
    )
    return result


async def run_eval_in_sandbox(
    code_files: dict[str, str],  # {filename: content}
    problem_dir: Path,           # 题目目录（含 test.c 等）
    timeout: int = 300,
    memory: str = "128m",
) -> EvalResult:
    """
    在本地运行评测（不使用 Docker 沙箱）
    """
    logger.info("run_eval_in_sandbox: start")
    import asyncio.subprocess

    result = EvalResult()

    # 读取外部评测脚本
    eval_script = EVAL_SCRIPT_PATH.read_text()

    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir)

        # 写入模型生成的代码
        for filename, content in code_files.items():
            (sandbox / filename).write_text(content)

        # 复制题目测试文件
        for f in problem_dir.iterdir():
            if f.name not in code_files and f.is_file():
                (sandbox / f.name).write_text(f.read_text())

        # 写入评测脚本
        (sandbox / "eval.sh").write_text(eval_script)
        os.chmod(sandbox / "eval.sh", 0o755)

        # 读取 problem.json 获取编译参数和并发标志
        extra_flags = ""
        scoring = {}
        concurrent = True
        problem_json = problem_dir / "problem.json"
        if problem_json.exists():
            pdata = json.loads(problem_json.read_text())
            extra_flags = pdata.get("compile_flags", "")
            scoring = pdata.get("scoring", {})
            concurrent = pdata.get("concurrent", True)

        try:
            cmd = [
                "bash", str(sandbox / "eval.sh"),
                str(sandbox / "result.json"),
                "solution.c",
                "",
                extra_flags,
                "1" if concurrent else "0",
            ]

            logger.info(f"Running evaluation: {' '.join(cmd[:3])} ...")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(sandbox),
            )

            stdout_bytes = None
            stderr_bytes = None
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
                returncode = process.returncode
                logger.info(f"Evaluation exit code: {returncode}")
                if stderr_bytes:
                    logger.debug(f"Evaluation stderr: {stderr_bytes.decode()}")
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result.timed_out = True
                result.error = "evaluation timed out"
                logger.warning(f"Evaluation timed out after {timeout}s")
            except Exception as e:
                process.kill()
                await process.wait()
                result.error = str(e)
                logger.error(f"Evaluation error: {e}")

            # 读取结果
            result_file = sandbox / "result.json"
            if result_file.exists():
                data = json.loads(result_file.read_text())
                logger.info(f"Result data keys: {list(data.keys())}")
                for key, value in data.items():
                    if hasattr(result, key):
                        setattr(result, key, value)
                logger.info(f"Compile success: {result.compile_success}")
                logger.info(f"Compile errors: {result.compile_errors[:100] if result.compile_errors else 'None'}")
            else:
                stdout_text = stdout_bytes.decode() if stdout_bytes else 'N/A'
                stderr_text = stderr_bytes.decode() if stderr_bytes else 'N/A'
                result.error = f"result.json not found; stdout: {stdout_text}, stderr: {stderr_text}"
                logger.error(result.error)

            # 从 stdout 解析 EXEC_TIME_MS
            if stdout_bytes:
                for line in stdout_bytes.decode(errors='replace').splitlines():
                    m = re.match(r'^EXEC_TIME_MS:(\d+)', line.strip())
                    if m:
                        result.exec_time_ms = int(m.group(1))
                        break

        except Exception as e:
            result.error = str(e)
            logger.error(f"Evaluation error: {e}")

    # 计算评分（concurrent 已在 with 块内读取）
    compute_scores(result, scoring, token_usage=None, concurrent=concurrent)
    return result
