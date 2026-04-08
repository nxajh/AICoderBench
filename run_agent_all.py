#!/usr/bin/env python3
"""Agent Runner: 用 agent 模式跑所有模型的 03-interpreter"""
import asyncio, sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import create_providers
from app.scheduler.agent_runner import run_agent
from app.evaluator.engine import run_eval_in_sandbox, compute_scores


async def run_one(label, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {label}")
    print(f"{'='*60}")

    start = time.time()
    agent_result = await run_agent(provider, problem, total_timeout=600)
    
    print(f"\n📊 Agent 结果:")
    print(f"   完成原因: {agent_result.finish_reason}")
    print(f"   轮次: {agent_result.rounds}")
    print(f"   耗时: {agent_result.total_time}s")
    print(f"   Token: {agent_result.total_token_usage}")
    
    for r in agent_result.history:
        tc_str = ", ".join(
            f"{tc['tool']}({tc.get('file','') or tc.get('compile_success','') or tc.get('test_success','') or tc.get('submitted','')})"
            for tc in r["tool_calls"]
        )
        print(f"   Round {r['round']} ({r['time']}s): {tc_str or r.get('note','')}")

    # 平台评分
    if "solution.c" in agent_result.files:
        print(f"\n🔧 平台评分中...")
        problem_dir = _find_problem_dir(problem.id)
        code_files = {"solution.c": agent_result.files["solution.c"]}
        eval_result = await run_eval_in_sandbox(code_files=code_files, problem_dir=problem_dir)
        scoring = problem.scoring.model_dump() if hasattr(problem.scoring, 'model_dump') else {}
        compute_scores(eval_result, scoring, token_usage=agent_result.total_token_usage)

        print(f"   编译: {'✅' if eval_result.compile_success else '❌'}")
        print(f"   测试: {eval_result.tests_passed}/{eval_result.tests_total}")
        print(f"   总分: {eval_result.score_total}/100")
        
        return {"label": label, "score": eval_result.score_total, 
                "tests": f"{eval_result.tests_passed}/{eval_result.tests_total}",
                "compile": eval_result.compile_success,
                "rounds": agent_result.rounds, "time": agent_result.total_time,
                "finish": agent_result.finish_reason}
    else:
        print(f"❌ 没有 solution.c")
        return {"label": label, "score": 0, "compile": False,
                "rounds": agent_result.rounds, "time": agent_result.total_time,
                "finish": agent_result.finish_reason}


async def main():
    problem = load_problem("03-interpreter")
    if not problem:
        print("❌ 题目不存在")
        return
    print(f"📚 题目: {problem.id} - {problem.title}")

    providers = create_providers()
    print(f"🤖 模型: {list(providers.keys())}")

    results = []
    for mid, prov in providers.items():
        try:
            r = await run_one(getattr(prov, 'provider_id', mid), prov, problem)
            results.append(r)
        except Exception as e:
            print(f"❌ {mid} 出错: {e}")
            results.append({"label": mid, "score": 0, "error": str(e)})

    print(f"\n{'='*60}")
    print("📊 总结")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['label']:20s} score={r.get('score',0):>3} tests={r.get('tests','N/A')} rounds={r.get('rounds','?')} time={r.get('time',0):.0f}s finish={r.get('finish','?')}")


if __name__ == "__main__":
    asyncio.run(main())
