#!/usr/bin/env python3
"""
端到端测试：1题 × 1模型，验证完整流水线
"""
import asyncio
import sys
import os
import json

# 确保能 import app
sys.path.insert(0, os.path.dirname(__file__))

from app.models.problem import load_problem, list_problems
from app.providers.model_provider import create_providers
from app.evaluator.engine import run_eval_in_sandbox
from app.scheduler.engine import build_prompt, run_single_submission, Submission
from app.config import RESULTS_DIR


async def test_e2e():
    print("=" * 60)
    print("AICoderBench 端到端测试")
    print("=" * 60)

    # 1. 检查题库
    problems = list_problems()
    print(f"\n📚 题库: {len(problems)} 道题")
    for p in problems:
        print(f"   - {p.id}: {p.title}")

    if not problems:
        print("❌ 没有找到题目")
        return

    problem = problems[0]
    print(f"\n🎯 使用题目: {problem.id} - {problem.title}")

    # 2. 检查模型
    providers = create_providers()
    print(f"\n🤖 可用模型: {list(providers.keys())}")

    if not providers:
        print("❌ 没有配置模型 API key")
        return

    model_id = list(providers.keys())[0]
    provider = providers[model_id]
    print(f"   使用模型: {model_id} ({provider.model})")

    # 3. 生成代码
    print(f"\n⏳ 正在调用 {model_id} 生成代码...")
    prompt = build_prompt(problem)
    print(f"   Prompt 长度: {len(prompt)} 字符")

    try:
        gen_result = await provider.generate(prompt)
        print(f"   ✅ 生成完成")
        print(f"   方式: {'tool calling' if gen_result.used_tool_call else '文本解析'}")
        print(f"   文件数: {len(gen_result.files)}")
        for f in gen_result.files:
            print(f"   - {f.path}: {len(f.content)} 字符")
            # 打印前5行预览
            lines = f.content.split('\n')[:5]
            for line in lines:
                print(f"     | {line}")
            if len(f.content.split('\n')) > 5:
                print(f"     | ... ({len(f.content.split(chr(10)))} lines total)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"   ❌ 生成失败: {e}")
        return

    # 4. 沙箱评测
    print(f"\n🔧 正在 Docker 沙箱中评测...")
    code_files = {f.path: f.content for f in gen_result.files}
    from app.models.problem import _find_problem_dir
    problem_dir = _find_problem_dir(problem.id)
    print(f"   题目目录: {problem_dir}")

    try:
        eval_result = await run_eval_in_sandbox(
            code_files=code_files,
            problem_dir=problem_dir,
            timeout=120,
        )
        print(f"   ✅ 评测完成")
        print(f"\n📊 评测结果:")
        print(f"   编译: {'✅ 通过' if eval_result.compile_success else '❌ 失败'}")
        if eval_result.compile_warnings:
            print(f"   Warnings: {eval_result.compile_warnings}")
        if eval_result.compile_errors:
            print(f"   Errors: {eval_result.compile_errors[:3]}")
        print(f"   测试: {eval_result.tests_passed}/{eval_result.tests_total}")
        if eval_result.tests_total > 0:
            print(f"   测试输出（最后几行）:")
            for line in eval_result.test_output.split('\n')[-5:]:
                print(f"     | {line}")
        print(f"   TSan issues: {eval_result.tsan_issues}")
        print(f"   ASan issues: {eval_result.asan_issues}")
        print(f"   cppcheck: {eval_result.cppcheck_errors} errors, {eval_result.cppcheck_warnings} warnings")
        print(f"   圈复杂度: max={eval_result.max_cyclomatic}, avg={eval_result.avg_cyclomatic}")
        print(f"   代码行数: {eval_result.total_loc}")
        print(f"\n🏆 评分:")
        print(f"   编译: {eval_result.score_compile}")
        print(f"   测试: {eval_result.score_tests}")
        print(f"   并发: {eval_result.score_concurrency}")
        print(f"   内存: {eval_result.score_memory}")
        print(f"   质量: {eval_result.score_quality}")
        print(f"   性能: {eval_result.score_performance}")
        print(f"   ─────────────")
        print(f"   总分: {eval_result.score_total}")

        if eval_result.error:
            print(f"\n   ⚠️ 错误: {eval_result.error}")
        if eval_result.timed_out:
            print(f"\n   ⚠️ 超时")

    except Exception as e:
        print(f"   ❌ 评测失败: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n{'=' * 60}")
    print("端到端测试完成！")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(test_e2e())
