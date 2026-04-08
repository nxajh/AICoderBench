#!/usr/bin/env python3
"""重跑 GLM-thinking agent 模式"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider
from app.scheduler.agent_runner import run_agent
from app.evaluator.engine import run_eval_in_sandbox, compute_scores


async def main():
    problem = load_problem("03-interpreter")
    provider = GLMProvider(
        api_key=os.getenv("GLM_API_KEY"),
        model=os.getenv("GLM_MODEL", "glm-5.1"),
        base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
        thinking=True,
    )

    print(f"📚 GLM-thinking Agent | 03-interpreter | timeout=7200s")
    
    agent_result = await run_agent(provider, problem, total_timeout=7200)
    
    print(f"\n📊 结果: finish={agent_result.finish_reason} rounds={agent_result.rounds} time={agent_result.total_time}s")
    print(f"   Token: {agent_result.total_token_usage}")
    
    for r in agent_result.history:
        tc_str = ", ".join(
            f"{tc['tool']}({tc.get('file','') or tc.get('compile_success','') or tc.get('test_success','') or tc.get('submitted','')})"
            for tc in r["tool_calls"]
        )
        print(f"   Round {r['round']} ({r['time']}s): {tc_str or r.get('note','')}")

    if "solution.c" in agent_result.files:
        problem_dir = _find_problem_dir(problem.id)
        eval_result = await run_eval_in_sandbox(code_files={"solution.c": agent_result.files["solution.c"]}, problem_dir=problem_dir)
        scoring = problem.scoring.model_dump() if hasattr(problem.scoring, 'model_dump') else {}
        compute_scores(eval_result, scoring, token_usage=agent_result.total_token_usage)
        print(f"\n🏆 编译={'✅' if eval_result.compile_success else '❌'} 测试={eval_result.tests_passed}/{eval_result.tests_total} 总分={eval_result.score_total}/100")

asyncio.run(main())
