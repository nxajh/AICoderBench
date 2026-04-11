"""
调度引擎 — 流水线调度器

架构：
  - 生成：多模型并行（同一模型的多道题串行，避免单模型 API 限流）
  - 评测：生成完成后立刻触发，不等待其他模型；信号量限制 Docker 容器数
  - 生成与评测完全重叠，消除两阶段串行等待
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

from ..providers.model_provider import ModelProvider
from ..evaluator.engine import run_eval_in_sandbox, compute_scores, EvalResult
from ..models.problem import Problem, load_problem, _find_problem_dir
from .agent_runner import run_agent, AgentRunResult
from ..config import SANDBOX_CONCURRENCY
from .. import database as db

logger = logging.getLogger(__name__)

GEN_TIMEOUT = 7200
MAX_429_RETRIES = 3
MAX_429_WAIT = 120


@dataclass
class GenTask:
    problem: Problem
    problem_id: str        # problems.id（文件系统目录名）
    model_uuid: str
    round_id: str
    provider: ModelProvider
    result: Optional[AgentRunResult] = None


@dataclass
class EvalTask:
    problem: Problem
    problem_id: str
    model_uuid: str
    round_id: str
    code_files: dict[str, str]
    token_usage: dict


def _is_429_error(exc: Exception) -> bool:
    return "429" in str(exc) or "rate_limit" in str(exc).lower()


async def _wait_with_backoff(attempt: int):
    wait_time = min(15 * (2 ** attempt), MAX_429_WAIT)
    logger.warning(f"429 rate limit, waiting {wait_time}s (attempt {attempt + 1}/{MAX_429_RETRIES})")
    await asyncio.sleep(wait_time)


async def run_benchmark(
    problem_ids: list[str],
    model_uuids: list[str],
    providers: dict[str, ModelProvider],
    round_name: str = "",
    round_id: str = "",
) -> str:
    if not round_id:
        round_id = f"round-{uuid.uuid4().hex[:8]}"
        await db.create_round(round_id, problem_ids, model_uuids, round_name)
        await db.update_round_status(round_id, "running")

    try:
        await _run_benchmark_inner(round_id, problem_ids, model_uuids, providers)
    except Exception as e:
        logger.error(f"Round {round_id}: unexpected error: {e}", exc_info=True)
        await db.update_round_status(round_id, "failed")
        subs = await db.get_submissions_by_round(round_id)
        for s in subs:
            if s.get("status") in ("pending", "generating", "evaluating"):
                await db.update_submission(
                    s["round_id"], s["problem_id"], s["model_uuid"],
                    status="failed",
                    generation_error=f"scheduler crash: {e}",
                    finished_at=datetime.utcnow().isoformat(),
                )
    return round_id


async def _run_benchmark_inner(
    round_id: str,
    problem_ids: list[str],
    model_uuids: list[str],
    providers: dict[str, ModelProvider],
) -> None:
    gen_tasks: list[GenTask] = []
    for pid in problem_ids:
        try:
            problem = load_problem(pid)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Problem not found, skipping {pid}: {e}")
            continue
        for mid in model_uuids:
            if mid not in providers:
                logger.warning(f"Model not configured: {mid}")
                continue
            gen_tasks.append(GenTask(
                problem=problem,
                problem_id=pid,
                model_uuid=mid,
                round_id=round_id,
                provider=providers[mid],
            ))

    if not gen_tasks:
        await db.update_round_status(round_id, "failed")
        return

    for task in gen_tasks:
        await db.create_submission(round_id, task.problem_id, task.model_uuid)

    n_models = len({t.model_uuid for t in gen_tasks})
    n_hosts = len({urlparse(t.provider.base_url).hostname for t in gen_tasks})
    logger.info(
        f"Round {round_id}: {len(gen_tasks)} tasks, "
        f"{n_models} models / {n_hosts} API hosts, eval_concurrency={SANDBOX_CONCURRENCY}"
    )

    eval_sem = asyncio.Semaphore(SANDBOX_CONCURRENCY)
    spawned_evals: list[asyncio.Task] = []

    async def _gen_then_eval(task: GenTask):
        success = await _attempt_gen_task(task)
        if not success or not task.result or not task.result.files.get("solution.c"):
            return
        eval_task = EvalTask(
            problem=task.problem,
            problem_id=task.problem_id,
            model_uuid=task.model_uuid,
            round_id=task.round_id,
            code_files=dict(task.result.files),
            token_usage=task.result.total_token_usage or {},
        )
        t = asyncio.create_task(_run_eval_with_sem(eval_task, eval_sem))
        spawned_evals.append(t)

    def _rate_limit_key(task: GenTask) -> str:
        host = urlparse(task.provider.base_url).hostname or task.provider.base_url
        return host

    by_host: dict[str, list[GenTask]] = {}
    for task in gen_tasks:
        by_host.setdefault(_rate_limit_key(task), []).append(task)

    async def _run_provider_group(tasks: list[GenTask]):
        for task in tasks:
            await _gen_then_eval(task)

    await asyncio.gather(*[_run_provider_group(tasks) for tasks in by_host.values()])

    if spawned_evals:
        await asyncio.gather(*spawned_evals, return_exceptions=True)

    await db.update_round_status(round_id, "done")


async def _attempt_gen_task(task: GenTask) -> bool:
    existing = await db.get_submission(task.round_id, task.problem_id, task.model_uuid)
    if existing and existing["status"] in ("done", "failed", "generated", "evaluating"):
        logger.info(f"Skip {task.problem_id}/{task.model_uuid[:8]}: already {existing['status']}")
        return existing["status"] == "generated"

    await db.update_submission(task.round_id, task.problem_id, task.model_uuid, status="generating")

    for attempt in range(MAX_429_RETRIES):
        try:
            async def _on_progress(round_num: int):
                await db.update_submission(task.round_id, task.problem_id, task.model_uuid, agent_round=round_num)

            result = await asyncio.wait_for(
                run_agent(task.provider, task.problem, total_timeout=GEN_TIMEOUT, on_progress=_on_progress),
                timeout=GEN_TIMEOUT + 60,
            )
            task.result = result

            if result and result.files.get("solution.c"):
                token_usage = result.total_token_usage or {}
                await db.update_submission(
                    task.round_id, task.problem_id, task.model_uuid,
                    status="generated",
                    generated_code=result.files["solution.c"],
                    generation_history=json.dumps(result.history, ensure_ascii=False)[:200000],
                    used_tool_call=1,
                    token_usage=json.dumps(token_usage),
                    generation_duration=result.total_time,
                    agent_round=result.rounds,
                )
                logger.info(
                    f"[{task.model_uuid[:8]}] {task.problem_id}: generated "
                    f"({result.rounds} rounds, {result.total_time:.1f}s, {result.finish_reason})"
                )
                return True
            else:
                error_msg = result.error if result else "no result"
                await db.update_submission(
                    task.round_id, task.problem_id, task.model_uuid,
                    status="failed",
                    generation_error=f"no solution: {error_msg}",
                    generation_duration=result.total_time if result else 0,
                    finished_at=datetime.utcnow().isoformat(),
                )
                logger.warning(f"[{task.model_uuid[:8]}] {task.problem_id}: no solution ({error_msg})")
                return False

        except asyncio.TimeoutError:
            logger.warning(f"[{task.model_uuid[:8]}] {task.problem_id}: timed out after {GEN_TIMEOUT}s")
            await db.update_submission(
                task.round_id, task.problem_id, task.model_uuid,
                status="failed",
                generation_error=f"generation timed out ({GEN_TIMEOUT}s)",
                finished_at=datetime.utcnow().isoformat(),
            )
            return False

        except Exception as e:
            if _is_429_error(e) and attempt < MAX_429_RETRIES - 1:
                await _wait_with_backoff(attempt)
                continue
            logger.error(f"[{task.model_uuid[:8]}] {task.problem_id}: error: {e}")
            await db.update_submission(
                task.round_id, task.problem_id, task.model_uuid,
                status="failed",
                generation_error=str(e)[:500],
                finished_at=datetime.utcnow().isoformat(),
            )
            return False

    return False


async def _run_eval_with_sem(task: EvalTask, sem: asyncio.Semaphore):
    async with sem:
        await _run_eval_task(task)


async def _run_eval_task(task: EvalTask):
    await db.update_submission(task.round_id, task.problem_id, task.model_uuid, status="evaluating")

    problem_dir = _find_problem_dir(task.problem.id)
    eval_result = await _eval_with_retry(task.code_files, problem_dir)

    problem_json = problem_dir / "problem.json"
    concurrent, perf_baseline_ms = True, 0
    if problem_json.exists():
        pdata = json.loads(problem_json.read_text())
        concurrent = pdata.get("concurrent", True)
        perf_baseline_ms = pdata.get("perf_baseline_ms", 0)

    scoring = task.problem.scoring.model_dump() if hasattr(task.problem.scoring, "model_dump") else {}
    scoring["perf_baseline_ms"] = perf_baseline_ms
    compute_scores(eval_result, scoring, token_usage=task.token_usage, concurrent=concurrent)

    score_breakdown = {
        "compile":     eval_result.score_compile,
        "tests":       eval_result.score_tests,
        "safety":      eval_result.score_safety,
        "quality":     eval_result.score_quality,
        "resource":    eval_result.score_resource,
        "performance": eval_result.score_performance,
    }
    expected = sum(score_breakdown.values())
    if expected != eval_result.score_total:
        logger.warning(
            f"[{task.model_uuid[:8]}] {task.problem_id}: "
            f"score_breakdown sum ({expected}) != score_total ({eval_result.score_total}), correcting"
        )
        eval_result.score_total = expected

    final_status = "done" if not eval_result.error else "failed"
    await db.update_submission(
        task.round_id, task.problem_id, task.model_uuid,
        status=final_status,
        eval_result=json.dumps(asdict(eval_result), ensure_ascii=False),
        total_score=eval_result.score_total,
        score_breakdown=json.dumps(score_breakdown),
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info(
        f"[{task.model_uuid[:8]}] {task.problem_id}: "
        f"compile={'✓' if eval_result.compile_success else '✗'} "
        f"tests={eval_result.tests_passed}/{eval_result.tests_total} "
        f"score={eval_result.score_total}"
    )


async def _eval_with_retry(code_files: dict, problem_dir: Path, max_retries: int = 2) -> EvalResult:
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return await run_eval_in_sandbox(code_files=code_files, problem_dir=problem_dir)
        except Exception as e:
            last_error = e
            logger.warning(f"eval attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)
    return EvalResult(error=str(last_error))
