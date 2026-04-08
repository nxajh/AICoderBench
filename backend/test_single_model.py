#!/usr/bin/env python3
"""
单模型评测工具

用法:
  python test_single_model.py minimax                          # 跑全部题
  python test_single_model.py minimax 03-interpreter           # 跑单题
  python test_single_model.py minimax 01 03 05                 # 跑多题
  python test_single_model.py minimax --show                   # 查看历史结果
  python test_single_model.py --summary                        # 汇总所有模型

每次运行结果追加到 results/<model_key>.jsonl，同一题多次跑记录所有分数。
汇总时计算每题最高分/最低分/平均分，总分同理。
"""
import asyncio, sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider, MiniMaxProvider, OpenRouterProvider
from app.scheduler.agent_runner import run_agent
from app.evaluator.engine import run_eval_in_sandbox, compute_scores

ALL_PROBLEMS = [
    "01-rate-limiter", "02-ring-buffer", "03-interpreter",
    "04-thread-safe-lru-cache", "05-mpmc-queue", "06-memory-pool",
    "07-cow-container", "08-concurrent-hashmap", "09-async-logger", "10-event-loop",
]

PROVIDERS = {
    "minimax": ("MiniMax-M2.7", lambda: MiniMaxProvider(
        api_key=os.getenv("MINIMAX_API_KEY", ""),
        model="MiniMax-M2.7",
        base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
    )),
    "glm": ("GLM-5.1 非思考", lambda: GLMProvider(
        api_key=os.getenv("GLM_API_KEY", ""),
        model="glm-5.1",
        base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
        thinking=False,
    )),
    "glm-thinking": ("GLM-5.1 思考", lambda: GLMProvider(
        api_key=os.getenv("GLM_API_KEY", ""),
        model="glm-5.1",
        base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"),
        thinking=True,
    )),
    "qwen": ("Qwen3.6-Plus", lambda: OpenRouterProvider(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        model="qwen/qwen3.6-plus:free",
        base_url="https://openrouter.ai/api/v1",
    )),
}

RESULTS_DIR = Path(__file__).parent.parent / "results"


# ─── 单次评测 ────────────────────────────────────────────
async def run_one(label, provider, problem):
    print(f"\n{'='*60}")
    print(f"🤖 {label} | {problem.id}")
    print(f"{'='*60}")

    start = time.time()
    try:
        agent_result = await run_agent(provider, problem)
    except Exception as e:
        print(f"❌ Agent 失败: {type(e).__name__}: {e}")
        return None

    elapsed = time.time() - start
    scoring_dict = problem.scoring.model_dump() if hasattr(problem.scoring, "model_dump") else dict(problem.scoring)

    eval_result = None
    try:
        eval_result = await run_eval_in_sandbox(
            code_files=agent_result.files,
            problem_dir=_find_problem_dir(problem.id),
        )
        compute_scores(eval_result, scoring_dict)
    except Exception as e:
        print(f"❌ 评测失败: {type(e).__name__}: {e}")

    result = {
        "model": label,
        "problem_id": problem.id,
        "finish_reason": agent_result.finish_reason,
        "rounds": agent_result.rounds,
        "time": round(elapsed, 1),
        "tokens": agent_result.total_token_usage,
        "tests_passed": eval_result.tests_passed if eval_result else 0,
        "tests_total": eval_result.tests_total if eval_result else 0,
        "tsan": eval_result.tsan_issues if eval_result else 0,
        "asan": eval_result.asan_issues if eval_result else 0,
        "score": eval_result.score_total if eval_result else 0,
        "scores": {k: getattr(eval_result, f"score_{k}", 0)
                   for k in ["compile","tests","concurrency","memory","quality","performance","efficiency"]
                  } if eval_result else {},
        "files": {f: len(c) for f, c in agent_result.files.items()},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    status = "✅" if eval_result and eval_result.score_total > 0 else "❌"
    print(f"{status} {result['score']}/100 | 测试 {result['tests_passed']}/{result['tests_total']} | "
          f"TSan={result['tsan']} | {result['rounds']}轮 | {result['time']}s")
    return result


# ─── 追加结果到 JSONL ────────────────────────────────────
def save_result(model_key, result):
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{model_key}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


# ─── 读取某模型所有历史结果 ────────────────────────────────
def load_results(model_key):
    path = RESULTS_DIR / f"{model_key}.jsonl"
    if not path.exists():
        return []
    results = []
    for line in open(path):
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results


# ─── 显示某模型结果 ──────────────────────────────────────
def show_model(model_key):
    label = PROVIDERS[model_key][0]
    results = load_results(model_key)
    if not results:
        print(f"📊 {label}: 暂无数据")
        return

    # 按 problem_id 分组
    by_problem = {}
    for r in results:
        pid = r["problem_id"]
        by_problem.setdefault(pid, []).append(r)

    print(f"\n{'='*70}")
    print(f"📊 {label} 历史结果 ({len(results)} 次提交)")
    print(f"{'='*70}")
    print(f"{'题目':<28} {'最高':>4} {'最低':>4} {'平均':>6} {'次数':>4}")
    print("-" * 70)

    all_max, all_min, all_sum, all_n = 0, 1000, 0, 0
    for pid in ALL_PROBLEMS:
        if pid not in by_problem:
            print(f"{pid:<28} {'--':>4} {'--':>4} {'--':>6} {'0':>4}")
            continue
        scores = [r["score"] for r in by_problem[pid]]
        mx, mn = max(scores), min(scores)
        avg = sum(scores) / len(scores)
        all_max += mx
        all_min += mn
        all_sum += sum(scores)
        all_n += len(scores)
        print(f"{pid:<28} {mx:>4} {mn:>4} {avg:>6.1f} {len(scores):>4}")

    print("-" * 70)
    if all_n > 0:
        print(f"{'总计(各题最高分求和)':<28} {all_max:>4}")
        print(f"{'总计(各题最低分求和)':<28} {all_min:>4}")
        print(f"{'平均(所有提交平均)':<28} {all_sum/all_n:>6.1f}")
    print()


# ─── 汇总所有模型 ────────────────────────────────────────
def show_summary():
    print(f"\n{'='*80}")
    print(f"📊 全模型汇总")
    print(f"{'='*80}")
    print(f"{'模型':<20} {'最高总分':>8} {'最低总分':>8} {'平均总分':>8} {'提交次数':>8}")
    print("-" * 80)

    for key in PROVIDERS:
        label = PROVIDERS[key][0]
        results = load_results(key)
        if not results:
            print(f"{label:<20} {'--':>8} {'--':>8} {'--':>8} {'0':>8}")
            continue

        by_problem = {}
        for r in results:
            by_problem.setdefault(r["problem_id"], []).append(r)

        max_total = sum(max(r["score"] for r in rs) for rs in by_problem.values())
        min_total = sum(min(r["score"] for r in rs) for rs in by_problem.values())
        avg_total = sum(r["score"] for r in results) / len(results)
        print(f"{label:<20} {max_total:>8} {min_total:>8} {avg_total:>8.1f} {len(results):>8}")

    # 各题明细
    print(f"\n{'='*80}")
    print(f"各题最高分对比")
    print(f"{'='*80}")
    header = f"{'题目':<28}"
    for key in PROVIDERS:
        header += f" {PROVIDERS[key][0]:>12}"
    print(header)
    print("-" * (28 + 13 * len(PROVIDERS)))

    for pid in ALL_PROBLEMS:
        row = f"{pid:<28}"
        for key in PROVIDERS:
            results = load_results(key)
            pr = [r for r in results if r["problem_id"] == pid]
            if pr:
                mx = max(r["score"] for r in pr)
                row += f" {mx:>12}"
            else:
                row += f" {'--':>12}"
        print(row)
    print()


# ─── 解析题目参数 ─────────────────────────────────────────
def resolve_problems(args_problems):
    if not args_problems:
        return ALL_PROBLEMS
    resolved = []
    for p in args_problems:
        # 支持简写: "01" -> "01-rate-limiter"
        matches = [pid for pid in ALL_PROBLEMS if pid == p or pid.startswith(p + "-")]
        if matches:
            resolved.extend(matches)
        else:
            print(f"⚠️ 未知题目: {p}")
    return resolved


# ─── main ─────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="AICoderBench 单模型评测")
    parser.add_argument("model", nargs="?", help="模型 key (minimax/glm/glm-thinking/qwen)")
    parser.add_argument("problems", nargs="*", help="题目 ID (空=全部)")
    parser.add_argument("--show", action="store_true", help="查看某模型历史结果")
    parser.add_argument("--summary", action="store_true", help="汇总所有模型")
    args = parser.parse_args()

    if args.summary:
        show_summary()
        return

    if not args.model:
        print("用法: python test_single_model.py <model_key> [problem_ids...]")
        print(f"可用模型: {', '.join(PROVIDERS.keys())}")
        print("选项: --show, --summary")
        return

    model_key = args.model
    if model_key not in PROVIDERS:
        print(f"未知模型: {model_key}")
        print(f"可用模型: {', '.join(PROVIDERS.keys())}")
        return

    if args.show:
        show_model(model_key)
        return

    label, provider_factory = PROVIDERS[model_key]
    provider = provider_factory()
    problems = resolve_problems(args.problems)

    print(f"🚀 模型: {label} | 题目: {len(problems)} 道")
    for pid in problems:
        print(f"  - {pid}")

    for pid in problems:
        problem = load_problem(pid)
        if not problem:
            print(f"⚠️ 题目 {pid} 不存在，跳过")
            continue
        result = await run_one(label, provider, problem)
        if result:
            save_result(model_key, result)
            print(f"💾 已保存到 results/{model_key}.jsonl")

    show_model(model_key)


if __name__ == "__main__":
    asyncio.run(main())
