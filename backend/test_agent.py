#!/usr/bin/env python3
"""测试 Agent 模式：GLM-5.1 非思考 vs 思考"""
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider
from app.scheduler.agent_runner import run_agent
from app.evaluator.engine import run_eval_in_sandbox, compute_scores


async def run_one(label, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {label}")
    print(f"{'='*60}")

    start = time.time()
    agent_result = await run_agent(provider, problem)
    
    print(f"\n📊 Agent 结果:")
    print(f"   完成原因: {agent_result.finish_reason}")
    print(f"   轮次: {agent_result.rounds}")
    print(f"   耗时: {agent_result.total_time}s")
    print(f"   Token: {agent_result.total_token_usage}")
    print(f"   文件: {list(agent_result.files.keys())}")
    
    for fname, content in agent_result.files.items():
        print(f"   {fname}: {len(content)} chars, {len(content.splitlines())} lines")
    
    print(f"\n📝 交互历史:")
    for r in agent_result.history:
        tc_str = ", ".join(
            f"{tc['tool']}({tc.get('file','') or tc.get('compile_success','') or tc.get('test_success','') or tc.get('submitted','')})"
            for tc in r["tool_calls"]
        )
        print(f"   Round {r['round']} ({r['time']}s): {tc_str or r.get('note', 'no action')}")

    # 平台评分
    if "solution.c" in agent_result.files:
        print(f"\n🔧 平台评分中...")
        problem_dir = _find_problem_dir(problem.id)
        code_files = {"solution.c": agent_result.files["solution.c"]}
        eval_result = await run_eval_in_sandbox(code_files=code_files, problem_dir=problem_dir)

        scoring = problem.scoring.model_dump() if hasattr(problem.scoring, 'model_dump') else {}
        compute_scores(eval_result, scoring, token_usage=agent_result.total_token_usage)

        print(f"   编译: {'✅' if eval_result.compile_success else '❌'}")
        if eval_result.compile_errors:
            print(f"   编译错误: {eval_result.compile_errors[:200]}")
        print(f"   测试: {eval_result.tests_passed}/{eval_result.tests_total}")
        print(f"   TSan: {eval_result.tsan_issues} | ASan: {eval_result.asan_issues}")
        print(f"   质量: cyclo_max={eval_result.max_cyclomatic}, LOC={eval_result.total_loc}")
        print(f"\n🏆 评分:")
        print(f"   编译={eval_result.score_compile} 测试={eval_result.score_tests} 并发={eval_result.score_concurrency}")
        print(f"   内存={eval_result.score_memory} 质量={eval_result.score_quality} 性能={eval_result.score_performance} 效率={eval_result.score_efficiency}")
        print(f"   总分: {eval_result.score_total}/100")
        
        return {
            "label": label,
            "finish_reason": agent_result.finish_reason,
            "rounds": agent_result.rounds,
            "time": agent_result.total_time,
            "tokens": agent_result.total_token_usage,
            "score": eval_result.score_total,
            "compile": eval_result.compile_success,
            "tests": f"{eval_result.tests_passed}/{eval_result.tests_total}",
        }
    else:
        print(f"\n❌ 没有 solution.c，无法评分")
        return {
            "label": label,
            "finish_reason": agent_result.finish_reason,
            "rounds": agent_result.rounds,
            "time": agent_result.total_time,
            "score": 0,
            "compile": False,
        }


async def main():
    problem = load_problem("03-interpreter")
    if not problem:
        print("❌ 题目不存在")
        return

    print(f"📚 题目: {problem.id} - {problem.title}")

    glm_key = os.getenv("GLM_API_KEY")
    if not glm_key:
        print("❌ GLM_API_KEY 未配置")
        return

    # 先跑非思考模式
    provider = GLMProvider(
        api_key=glm_key,
        model="glm-5.1",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        thinking=True,
    )

    r = await run_one("GLM-5.1 思考 (Agent)", provider, problem)
    
    print(f"\n{'='*60}")
    print("📊 总结")
    print(f"{'='*60}")
    print(f"  {r['label']}: {r.get('score', 0)}分 | {r['rounds']}轮 | {r['time']}s | 测试{r.get('tests', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
