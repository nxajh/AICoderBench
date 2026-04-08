#!/usr/bin/env python3
"""全量评测：3模型 × 10题 Agent 模式"""
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider, MiniMaxProvider, OpenRouterProvider
from app.scheduler.agent_runner import run_agent
from app.evaluator.engine import run_eval_in_sandbox, compute_scores

PROBLEM_IDS = [
    "01-rate-limiter",
    "02-ring-buffer",
    "03-interpreter",
    "04-thread-safe-lru-cache",
    "05-mpmc-queue",
    "06-memory-pool",
    "07-cow-container",
    "08-concurrent-hashmap",
    "09-async-logger",
    "10-event-loop",
]


async def run_one(label, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {label}")
    print(f"{'='*60}")

    start = time.time()
    try:
        agent_result = await run_agent(provider, problem)
    except Exception as e:
        print(f"❌ Agent 运行失败: {type(e).__name__}: {e}")
        return {"label": label, "error": str(e), "time": time.time() - start}

    elapsed = time.time() - start

    print(f"\n📊 Agent 结果:")
    print(f"   完成原因: {agent_result.finish_reason}")
    print(f"   轮次: {agent_result.rounds}")
    print(f"   耗时: {elapsed:.1f}s")
    print(f"   Token: {agent_result.total_token_usage}")
    files_str = ", ".join(agent_result.files.keys())
    print(f"   文件: [{files_str}]")
    for fname, content in agent_result.files.items():
        print(f"   {fname}: {len(content)} chars, {content.count(chr(10))+1} lines")

    # 打印交互历史
    print(f"\n📝 交互历史:")
    for i, step in enumerate(agent_result.history, 1):
        dur = step.get("time", 0)
        tools = step.get("tool_calls", [])
        if tools:
            tool_str = ", ".join(f"{t.get('name','?')}({','.join(str(v) for v in t.get('args',{}).values())})" for t in tools)
        else:
            tool_str = step.get("note", "text only")
        print(f"   Round {i} ({dur}s): {tool_str}")

    # 评测
    print(f"\n🔧 平台评分中...")
    eval_result = await run_eval_in_sandbox(
        code_files=agent_result.files,
        problem_dir=_find_problem_dir(problem.id),
    )
    scoring_dict = problem.scoring.model_dump() if hasattr(problem.scoring, 'model_dump') else dict(problem.scoring)
    scores = compute_scores(eval_result, scoring_dict)

    print(f"\n🏆 评分:")
    print(f"   编译={'✅' if eval_result.compile_success else '❌'}")
    print(f"   测试: {eval_result.tests_passed}/{eval_result.tests_total}")
    print(f"   TSan: {eval_result.tsan_issues} | ASan: {eval_result.asan_issues}")
    print(f"   质量: cyclo_max={eval_result.max_cyclomatic}, LOC={eval_result.total_loc}")

    score_items = {k: v for k, v in eval_result.__dict__.items() if k.startswith("score_") and k != "score_total"}
    total = eval_result.score_total
    print(f"\n🏆 评分:")
    for k in ["compile", "tests", "concurrency", "memory", "quality", "performance", "efficiency"]:
        v = getattr(eval_result, f"score_{k}", 0)
        print(f"   {k}={v}", end=" ")
    print(f"\n   总分: {total}/100")

    return {
        "label": label,
        "problem_id": problem.id,
        "finish_reason": agent_result.finish_reason,
        "rounds": agent_result.rounds,
        "time": elapsed,
        "tokens": agent_result.total_token_usage,
        "tests": f"{eval_result.tests_passed}/{eval_result.tests_total}",
        "tests_passed": eval_result.tests_passed,
        "tests_total": eval_result.tests_total,
        "tsan": eval_result.tsan_issues,
        "asan": eval_result.asan_issues,
        "score": total,
        "scores": {k: getattr(eval_result, f"score_{k}", 0) for k in ["compile", "tests", "concurrency", "memory", "quality", "performance", "efficiency"]},
        "files": {fname: len(content) for fname, content in agent_result.files.items()},
    }


async def main():
    glm_key = os.getenv("GLM_API_KEY")
    minimax_key = os.getenv("MINIMAX_API_KEY")
    if not glm_key:
        print("❌ GLM_API_KEY 未配置"); return

    configs = [
        ("MiniMax-M2.7", MiniMaxProvider(
            api_key=minimax_key or "",
            model="MiniMax-M2.7",
            base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
        )),
        ("GLM-5.1 非思考", GLMProvider(
            api_key=glm_key,
            model="glm-5.1",
            base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
            thinking=False,
        )),
        ("GLM-5.1 思考", GLMProvider(
            api_key=glm_key,
            model="glm-5.1",
            base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
            thinking=True,
        )),
        ("Qwen3.6-Plus (OpenRouter)", OpenRouterProvider(
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            model="qwen/qwen3.6-plus:free",
            base_url="https://openrouter.ai/api/v1",
        )),
    ]

    all_results = []

    for pid in PROBLEM_IDS:
        problem = load_problem(pid)
        if not problem:
            print(f"\n⚠️ 题目 {pid} 不存在，跳过")
            continue

        print(f"\n\n{'#'*70}")
        print(f"# 📚 题目: {problem.id} - {problem.title}")
        print(f"{'#'*70}")

        for label, provider in configs:
            r = await run_one(label, provider, problem)
            all_results.append(r)

    # 最终汇总
    print(f"\n\n{'#'*70}")
    print(f"# 📊 全量评测汇总")
    print(f"{'#'*70}")
    print(f"{'模型':<20} {'题目':<25} {'分数':>6} {'轮次':>4} {'耗时':>8} {'测试':>8} {'TSan':>4}")
    print("-" * 80)
    for r in all_results:
        if "error" in r:
            print(f"{r['label']:<20} {r.get('problem_id','?'):<25} {'ERR':>6} {'?':>4} {r['time']:>7.1f}s {'?':>8} {'?':>4}")
        else:
            print(f"{r['label']:<20} {r['problem_id']:<25} {r['score']:>4}/100 {r['rounds']:>4} {r['time']:>7.1f}s {r['tests']:>8} {r.get('tsan',0):>4}")

    # 按模型汇总
    print(f"\n📊 模型总分:")
    for label, _ in configs:
        model_results = [r for r in all_results if r["label"] == label]
        total_score = sum(r.get("score", 0) for r in model_results)
        avg_score = total_score / len(model_results) if model_results else 0
        success = sum(1 for r in model_results if "error" not in r)
        print(f"  {label}: 总分={total_score} 平均={avg_score:.1f} 成功={success}/{len(model_results)}")

    # 保存 JSON
    out_file = Path(__file__).parent.parent / "results" / f"full_benchmark_{int(time.time())}.json"
    out_file.parent.mkdir(exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 结果已保存: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
