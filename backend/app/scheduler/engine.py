"""
调度引擎 — 双队列调度器（Generation Queue + Evaluation Queue）

- Generation Queue：走 agent_runner.run_agent()，模型 submit 后任务完成
- Evaluation Queue：走 run_eval_in_sandbox + compute_scores
- 429 处理：遇到 429 保存 checkpoint，切到其他模型，限流恢复后恢复
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..providers.model_provider import ModelProvider
from ..evaluator.engine import run_eval_in_sandbox, compute_scores, EvalResult
from ..models.problem import Problem, load_problem, list_problems, _find_problem_dir
from .agent_runner import run_agent, AgentRunResult
from .. import database as db

logger = logging.getLogger(__name__)

GEN_TIMEOUT = 7200  # 单个 agent 运行超时 2 小时
MAX_429_RETRIES = 3
MAX_429_WAIT = 120  # 单次等待最多 120s


# ---- Checkpoint 结构 ----

@dataclass
class GenCheckpoint:
    """429 时保存的中间状态"""
    problem_id: str
    model_uuid: str
    messages: list[dict] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    round_num: int = 0


# ---- Task 定义 ----

@dataclass
class GenTask:
    """Generation 阶段的任务"""
    problem: Problem
    problem_uuid: str  # 数据库 uuid
    model_uuid: str
    provider: ModelProvider
    sub_id: int = 0
    status: str = "pending"  # pending | running | done | failed | checkpointed
    checkpoint: Optional[GenCheckpoint] = None
    result: Optional[AgentRunResult] = None


@dataclass
class EvalTask:
    """Evaluation 阶段的任务"""
    problem: Problem
    model_uuid: str
    code_files: dict[str, str]
    token_usage: dict
    sub_id: int


# ---- 辅助函数 ----

def _is_429_error(exc: Exception) -> bool:
    return "429" in str(exc) or "rate_limit" in str(exc).lower()


async def _wait_with_backoff(attempt: int) -> bool:
    """指数退避等待"""
    wait_time = min(15 * (2 ** attempt), MAX_429_WAIT)
    logger.warning(f"429 rate limit, waiting {wait_time}s (attempt {attempt + 1}/{MAX_429_RETRIES})")
    await asyncio.sleep(wait_time)
    return True


# ---- 主调度器 ----

async def run_benchmark(
    problem_ids: list[str],
    model_uuids: list[str],
    providers: dict[str, ModelProvider],
    round_name: str = "",
) -> str:
    """
    主入口：创建 round，构建双队列，串行调度
    """
    round_id = f"round-{uuid.uuid4().hex[:8]}"
    await db.create_round(round_id, problem_ids, model_uuids, round_name)
    await db.update_round_status(round_id, "running")

    # 构建 generation tasks
    gen_tasks: list[GenTask] = []
    for pid in problem_ids:
        # pid 可能是 uuid，需要转为 slug 来加载文件
        slug = await db.get_problem_slug_by_uuid(pid)
        problem = load_problem(slug or pid)
        if not problem:
            logger.warning(f"Problem not found: {pid}")
            continue
        for mid in model_uuids:
            if mid not in providers:
                logger.warning(f"Model not configured: {mid}")
                continue
            gen_tasks.append(GenTask(problem=problem, problem_uuid=pid, model_uuid=mid, provider=providers[mid]))

    if not gen_tasks:
        await db.update_round_status(round_id, "failed")
        return round_id

    logger.info(f"Round {round_id}: {len(gen_tasks)} generation tasks")

    # 为每个 task 创建 DB submission 并记录 sub_id
    for task in gen_tasks:
        task.sub_id = await db.create_submission(round_id, task.problem_uuid, task.model_uuid)

    # Evaluation queue：generation 完成后推入
    eval_queue: list[EvalTask] = []

    # ---- Phase 1: Generation ----
    await _run_generation_phase(round_id, gen_tasks, eval_queue)

    # ---- Phase 2: Evaluation ----
    await _run_evaluation_phase(round_id, eval_queue)

    await db.update_round_status(round_id, "done")
    return round_id


async def _process_single_gen_task(task: GenTask) -> bool:
    """
    处理单个 generation task。
    返回 True 表示成功生成了代码（推入 eval queue 由调用者处理）。
    """
    result = await asyncio.wait_for(
        run_agent(task.provider, task.problem, total_timeout=GEN_TIMEOUT),
        timeout=GEN_TIMEOUT + 60,
    )
    task.result = result
    task.status = "done"
    return True


async def _run_generation_phase(
    round_id: str,
    gen_tasks: list[GenTask],
    eval_queue: list[EvalTask],
):
    """
    Generation 阶段：逐个执行 agent_runner
    遇到 429 保存 checkpoint，跳到下一个 task
    最后尝试恢复 checkpointed 的 tasks
    """
    checkpointed: list[GenTask] = []

    for task in gen_tasks:
        # 跳过已完成的（断点续跑场景）
        existing = await db.get_submission(round_id, task.problem_uuid, task.model_uuid)
        if existing and existing["status"] in ("done", "failed", "generated", "evaluating"):
            logger.info(f"Skipping {task.problem.id}/{task.model_uuid}: already {existing['status']}")
            continue

        task.status = "running"
        success = False

        for attempt in range(MAX_429_RETRIES):
            try:
                await _process_single_gen_task(task)
                success = True
                break
            except asyncio.TimeoutError:
                logger.warning(f"[{task.model_uuid}] {task.problem.id}: generation timed out ({GEN_TIMEOUT}s)")
                await db.update_submission(
                    task.sub_id, status="failed",
                    generation_error=f"generation timed out ({GEN_TIMEOUT}s)",
                    finished_at=datetime.utcnow().isoformat(),
                )
                task.status = "failed"
                break

            except Exception as e:
                if _is_429_error(e):
                    if attempt < MAX_429_RETRIES - 1:
                        await _wait_with_backoff(attempt)
                        continue
                    # 超过重试次数，保存 checkpoint
                    logger.warning(f"[{task.model_uuid}] {task.problem.id}: 429 exhausted, checkpointing")
                    task.status = "checkpointed"
                    task.checkpoint = GenCheckpoint(
                        problem_id=task.problem_uuid,
                        model_uuid=task.model_uuid,
                    )
                    await db.update_submission(
                        task.sub_id, status="failed",
                        generation_error=f"rate limited after {MAX_429_RETRIES} retries: {str(e)[:200]}",
                        finished_at=datetime.utcnow().isoformat(),
                    )
                    checkpointed.append(task)
                    break
                else:
                    logger.error(f"[{task.model_uuid}] {task.problem.id}: generation error: {e}")
                    await db.update_submission(
                        task.sub_id, status="failed",
                        generation_error=str(e)[:500],
                        finished_at=datetime.utcnow().isoformat(),
                    )
                    task.status = "failed"
                    break

        if not success:
            continue

        # 处理成功结果
        result = task.result
        if not result or not result.files.get("solution.c"):
            error_msg = result.error if result else "no result"
            logger.warning(f"[{task.model_uuid}] {task.problem.id}: no solution generated ({error_msg})")
            await db.update_submission(
                task.sub_id, status="failed",
                generation_error=f"agent finished without solution: {error_msg}",
                generation_duration=result.total_time if result else 0,
                finished_at=datetime.utcnow().isoformat(),
            )
            continue

        code = result.files["solution.c"]
        token_usage = result.total_token_usage or {}

        await db.update_submission(
            task.sub_id,
            status="generated",
            generated_code=code,
            raw_output=json.dumps(result.history, ensure_ascii=False)[:100000],
            used_tool_call=1,
            token_usage=json.dumps(token_usage),
            generation_duration=result.total_time,
        )

        logger.info(
            f"[{task.model_uuid}] {task.problem.id}: generated "
            f"({result.rounds} rounds, {result.total_time:.1f}s, "
            f"finish={result.finish_reason})"
        )

        # 推入 evaluation queue
        eval_queue.append(EvalTask(
            problem=task.problem,
            model_uuid=task.model_uuid,
            code_files=dict(result.files),
            token_usage=token_usage,
            sub_id=task.sub_id,
        ))

    # 恢复 checkpointed tasks
    if checkpointed:
        logger.info(f"Attempting recovery for {len(checkpointed)} checkpointed tasks")
        await asyncio.sleep(30)
        for task in checkpointed:
            task.status = "running"
            try:
                await _process_single_gen_task(task)
                if task.result and task.result.files.get("solution.c"):
                    code = task.result.files["solution.c"]
                    token_usage = task.result.total_token_usage or {}
                    await db.update_submission(
                        task.sub_id,
                        status="generated",
                        generated_code=code,
                        raw_output=json.dumps(task.result.history, ensure_ascii=False)[:100000],
                        used_tool_call=1,
                        token_usage=json.dumps(token_usage),
                        generation_duration=task.result.total_time,
                    )
                    eval_queue.append(EvalTask(
                        problem=task.problem,
                        model_uuid=task.model_uuid,
                        code_files=dict(task.result.files),
                        token_usage=token_usage,
                        sub_id=task.sub_id,
                    ))
                    logger.info(f"[{task.model_uuid}] {task.problem.id}: recovery successful")
                else:
                    logger.warning(f"[{task.model_uuid}] {task.problem.id}: recovery produced no solution")
            except Exception as e:
                logger.error(f"[{task.model_uuid}] {task.problem.id}: recovery failed: {e}")


async def _run_evaluation_phase(
    round_id: str,
    eval_queue: list[EvalTask],
):
    """
    Evaluation 阶段：顺序执行沙箱评测
    Docker 资源有限，不并行
    """
    for task in eval_queue:
        await db.update_submission(task.sub_id, status="evaluating")

        problem_dir = _find_problem_dir(task.problem.id)

        # 评测（带简单重试）
        eval_result = await _eval_with_retry(task.code_files, problem_dir)

        # 读取 problem.json 获取 concurrent 和 perf_baseline_ms
        problem_json = problem_dir / "problem.json"
        concurrent = True
        perf_baseline_ms = 0
        if problem_json.exists():
            pdata = json.loads(problem_json.read_text())
            concurrent = pdata.get("concurrent", True)
            perf_baseline_ms = pdata.get("perf_baseline_ms", 0)

        # 计算分数
        scoring = task.problem.scoring.model_dump() if hasattr(task.problem.scoring, 'model_dump') else {}
        scoring["perf_baseline_ms"] = perf_baseline_ms
        compute_scores(eval_result, scoring, token_usage=task.token_usage, concurrent=concurrent)

        score_breakdown = {
            "compile": eval_result.score_compile,
            "tests": eval_result.score_tests,
            "safety": eval_result.score_safety,
            "quality": eval_result.score_quality,
            "resource": eval_result.score_resource,
            "performance": eval_result.score_performance,
        }

        final_status = "done" if not eval_result.error else "failed"
        await db.update_submission(
            task.sub_id,
            status=final_status,
            eval_result=json.dumps(asdict(eval_result), ensure_ascii=False),
            total_score=eval_result.score_total,
            score_breakdown=json.dumps(score_breakdown),
            finished_at=datetime.utcnow().isoformat(),
        )

        logger.info(
            f"[{task.model_uuid}] {task.problem.id}: "
            f"compile={'✓' if eval_result.compile_success else '✗'} "
            f"tests={eval_result.tests_passed}/{eval_result.tests_total} "
            f"score={eval_result.score_total}"
        )


async def _eval_with_retry(code_files: dict, problem_dir: Path, max_retries: int = 2) -> EvalResult:
    """评测重试"""
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
