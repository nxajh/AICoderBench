#!/usr/bin/env python3
"""对比 GLM-5.1 vs MiniMax 在 interpreter 题目上"""
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import create_providers
from app.evaluator.engine import run_eval_in_sandbox, compute_scores
from app.scheduler.engine import build_prompt


async def run_one(model_id, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {model_id} ({provider.model})")
    print(f"{'='*60}")
    
    prompt = build_prompt(problem)
    print(f"Prompt: {len(prompt)} chars")
    
    # 生成
    print("⏳ 生成中...")
    start = time.time()
    try:
        gen = await provider.generate(prompt)
        elapsed = time.time() - start
        print(f"✅ 生成完成: {elapsed:.1f}s")
        print(f"   方式: {'tool calling' if gen.used_tool_call else '文本解析'}")
        print(f"   Token: {gen.token_usage}")
        if gen.files:
            code = gen.files[0].content
            print(f"   代码: {len(code)} chars, {len(code.splitlines())} lines")
        else:
            print(f"   ❌ 没有生成代码")
            return None
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 生成失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
        return None
    
    # 评测
    print("🔧 评测中...")
    code_files = {f.path: f.content for f in gen.files}
    problem_dir = _find_problem_dir(problem.id)
    
    eval_result = await run_eval_in_sandbox(code_files=code_files, problem_dir=problem_dir)
    
    scoring = problem.scoring.model_dump() if hasattr(problem.scoring, 'model_dump') else {}
    compute_scores(eval_result, scoring, token_usage=gen.token_usage)
    
    print(f"   编译: {'✅' if eval_result.compile_success else '❌'}")
    if eval_result.compile_errors:
        print(f"   错误: {eval_result.compile_errors[:200]}")
    print(f"   测试: {eval_result.tests_passed}/{eval_result.tests_total}")
    print(f"   TSan: {eval_result.tsan_issues} issues")
    print(f"   ASan: {eval_result.asan_issues} issues")
    print(f"   质量: cppcheck {eval_result.cppcheck_errors}err/{eval_result.cppcheck_warnings}warn, cyclomatic max={eval_result.max_cyclomatic}")
    print(f"   LOC: {eval_result.total_loc}")
    print(f"\n🏆 评分:")
    print(f"   编译={eval_result.score_compile} 测试={eval_result.score_tests} 并发={eval_result.score_concurrency}")
    print(f"   内存={eval_result.score_memory} 质量={eval_result.score_quality} 性能={eval_result.score_performance} 效率={eval_result.score_efficiency}")
    print(f"   总分: {eval_result.score_total}/100")
    
    return {
        "model": model_id,
        "gen_time": elapsed,
        "gen_method": "tool_call" if gen.used_tool_call else "text",
        "token_usage": gen.token_usage,
        "code_lines": len(code.splitlines()),
        "score_total": eval_result.score_total,
        "scores": {
            "compile": eval_result.score_compile,
            "tests": eval_result.score_tests,
            "concurrency": eval_result.score_concurrency,
            "memory": eval_result.score_memory,
            "quality": eval_result.score_quality,
            "performance": eval_result.score_performance,
            "efficiency": eval_result.score_efficiency,
        },
        "compile_ok": eval_result.compile_success,
        "tests": f"{eval_result.tests_passed}/{eval_result.tests_total}",
        "tsan": eval_result.tsan_issues,
        "asan": eval_result.asan_issues,
    }


async def main():
    problem = load_problem("03-interpreter")
    if not problem:
        print("❌ 题目不存在")
        return
    
    print(f"📚 题目: {problem.id} - {problem.title}")
    
    providers = create_providers()
    print(f"🤖 可用模型: {list(providers.keys())}")
    
    if not providers:
        print("❌ 没有配置模型")
        return
    
    results = []
    for mid, prov in providers.items():
        r = await run_one(mid, prov, problem)
        if r:
            results.append(r)
    
    # 对比
    print(f"\n{'='*60}")
    print("📊 对比总结")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['model']}: {r['score_total']}分 | {r['gen_time']:.0f}s | {r['code_lines']}行 | {r['tests']}")
        print(f"    token: {r['token_usage']}")


if __name__ == "__main__":
    asyncio.run(main())
