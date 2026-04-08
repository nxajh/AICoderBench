#!/usr/bin/env python3
"""GLM 思考 vs 非思考 对比（MiniMax key 失效，跳过）"""
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider
from app.evaluator.engine import run_eval_in_sandbox, compute_scores
from app.scheduler.engine import build_prompt


async def run_one(label, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {label}")
    print(f"{'='*60}")
    
    prompt = build_prompt(problem)
    print(f"Prompt: {len(prompt)} chars")
    
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
    print(f"   TSan: {eval_result.tsan_issues} | ASan: {eval_result.asan_issues}")
    print(f"   质量: cyclomatic max={eval_result.max_cyclomatic}, LOC={eval_result.total_loc}")
    print(f"\n🏆 评分: 总分 {eval_result.score_total}/100")
    print(f"   编译={eval_result.score_compile} 测试={eval_result.score_tests} 并发={eval_result.score_concurrency} 内存={eval_result.score_memory} 质量={eval_result.score_quality} 性能={eval_result.score_performance} 效率={eval_result.score_efficiency}")
    
    return {
        "label": label,
        "gen_time": round(elapsed, 1),
        "token_usage": gen.token_usage,
        "code_lines": len(code.splitlines()),
        "score_total": eval_result.score_total,
        "compile_ok": eval_result.compile_success,
        "tests": f"{eval_result.tests_passed}/{eval_result.tests_total}",
    }


async def main():
    problem = load_problem("03-interpreter")
    print(f"📚 {problem.id} - {problem.title}")
    
    glm_key = os.getenv("GLM_API_KEY")
    
    configs = [
        ("GLM-5.1 (非思考)", GLMProvider(api_key=glm_key, model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/coding/paas/v4", thinking=False)),
        ("GLM-5.1 (思考)", GLMProvider(api_key=glm_key, model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/coding/paas/v4", thinking=True)),
    ]
    
    results = []
    for label, provider in configs:
        r = await run_one(label, provider, problem)
        results.append(r or {"label": label, "error": True})
    
    print(f"\n{'='*60}")
    print("📊 对比")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  {r['label']}: ❌ 失败")
        else:
            rt = r['token_usage']
            reasoning = rt.get('completion_tokens_details', {}).get('reasoning_tokens', 0) if isinstance(rt, dict) else 0
            print(f"  {r['label']}: {r['score_total']}分 | {r['gen_time']}s | {r['code_lines']}行 | 测试{r['tests']} | reasoning={reasoning}")


if __name__ == "__main__":
    asyncio.run(main())
