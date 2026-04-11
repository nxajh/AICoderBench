"""
AICoderBench API 路由
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from pydantic import BaseModel

from ..models.problem import load_problem, create_problem, update_problem, delete_problem, update_test_file
from ..providers.model_provider import create_providers_from_db
from ..scheduler.engine import run_benchmark
from .. import database as db

router = APIRouter()


# ---- Pydantic 模型 ----

class CreateProviderRequest(BaseModel):
    name: str
    api_format: str = "openai"   # "openai" | "anthropic"
    api_key: str
    base_url: str = ""


class UpdateProviderRequest(BaseModel):
    name: Optional[str] = None
    api_format: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class CreateModelRequest(BaseModel):
    provider_uuid: str
    model_id: str
    thinking: bool = False
    thinking_budget: int = 10000
    max_tokens: int = 65536


class UpdateModelRequest(BaseModel):
    model_id: Optional[str] = None
    thinking: Optional[bool] = None
    thinking_budget: Optional[int] = None
    enabled: Optional[bool] = None
    max_tokens: Optional[int] = None


class CreateRoundRequest(BaseModel):
    name: str = ""
    problem_ids: Optional[list[str]] = None
    model_uuids: Optional[list[str]] = None


class CreateProblemRequest(BaseModel):
    id: str = ""
    slug: str = ""
    title: str
    difficulty: str = "medium"
    tags: list[str] = []
    language: str = "c"
    compile_flags: str = ""
    timeout_seconds: int = 30
    scoring: Optional[dict] = None
    description: str = ""
    interface_h: str = ""


class UpdateProblemRequest(BaseModel):
    title: Optional[str] = None
    difficulty: Optional[str] = None
    tags: Optional[list[str]] = None
    language: Optional[str] = None
    compile_flags: Optional[str] = None
    timeout_seconds: Optional[int] = None
    scoring: Optional[dict] = None
    description: Optional[str] = None
    interface_h: Optional[str] = None


class UpdateTestFileRequest(BaseModel):
    test_c: str = ""


# ---- 健康检查 ----

@router.get("/health")
async def health():
    return {"status": "ok"}


# ---- 排行榜 ----

@router.get("/global-leaderboard")
async def global_leaderboard():
    return await db.get_global_leaderboard()


@router.get("/problem-leaderboard/{problem_id}")
async def problem_leaderboard(problem_id: str):
    return await db.get_problem_leaderboard(problem_id, limit=10)


# ---- 题目 ----

@router.get("/problems")
async def get_problems():
    problems_meta = await db.list_problems_db()
    result = []
    for p in problems_meta:
        try:
            file_data = load_problem(p["id"])
            result.append({**p, "description": file_data.description, "interface_h": file_data.interface_h})
        except FileNotFoundError:
            result.append(p)
    return result


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: str):
    p = await db.get_problem(problem_id)
    if not p:
        raise HTTPException(404, f"Problem '{problem_id}' not found")
    try:
        file_data = load_problem(p["id"])
        return {**p, "description": file_data.description, "interface_h": file_data.interface_h}
    except FileNotFoundError:
        return p


@router.post("/problems")
async def create_problem_api(req: CreateProblemRequest):
    import re
    if not req.title.strip():
        raise HTTPException(400, "标题不能为空")

    problem_id = req.id.strip()
    if not problem_id:
        from ..config import PROBLEMS_DIR
        existing = [d for d in PROBLEMS_DIR.iterdir() if d.is_dir() and (d / "problem.json").exists()] if PROBLEMS_DIR.exists() else []
        next_num = len(existing) + 1
        slug = req.slug.strip()
        if slug:
            if not re.match(r"^[a-zA-Z0-9_-]+$", slug):
                raise HTTPException(400, "英文标识只能包含字母、数字、下划线和连字符")
            problem_id = f"{next_num:02d}-{slug}"
        else:
            problem_id = f"{next_num:02d}"
    elif not re.match(r"^[a-zA-Z0-9_-]+$", problem_id):
        raise HTTPException(400, "ID 只能包含字母、数字、下划线和连字符")

    if req.scoring:
        weight_total = sum(v for v in req.scoring.values() if isinstance(v, (int, float)))
        if weight_total != 100:
            raise HTTPException(400, f"scoring 权重之和须为 100，当前为 {weight_total}")
    try:
        create_problem(
            id=problem_id,
            title=req.title,
            difficulty=req.difficulty,
            tags=req.tags,
            language=req.language,
            compile_flags=req.compile_flags,
            timeout_seconds=req.timeout_seconds,
            scoring=req.scoring,
            description=req.description,
            interface_h=req.interface_h,
        )
        await db.sync_problems_from_disk()
        p = await db.get_problem(problem_id)
        return p
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@router.put("/problems/{problem_id}")
async def update_problem_api(problem_id: str, req: UpdateProblemRequest):
    if req.scoring is not None:
        weight_total = sum(v for v in req.scoring.values() if isinstance(v, (int, float)))
        if weight_total != 100:
            raise HTTPException(400, f"scoring 权重之和须为 100，当前为 {weight_total}")
    try:
        updated = update_problem(
            problem_id=problem_id,
            **{k: v for k, v in req.model_dump().items() if v is not None},
        )
        await db.sync_problems_from_disk()
        fresh = await db.get_problem(problem_id)
        if fresh:
            return {**fresh, "description": updated.description, "interface_h": updated.interface_h}
        return updated.model_dump()
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.delete("/problems/{problem_id}")
async def delete_problem_api(problem_id: str):
    conn = await db.get_db()
    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM submissions WHERE problem_id=?", (problem_id,)
    ) as cur:
        row = await cur.fetchone()
        if row and row["cnt"] > 0:
            raise HTTPException(400, f"该题目有 {row['cnt']} 条提交记录，无法删除")
    try:
        delete_problem(problem_id)
        await conn.execute("DELETE FROM problems WHERE id=?", (problem_id,))
        await conn.commit()
        return {"status": "deleted"}
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.post("/problems/{problem_id}/test-file")
async def upload_test_file(problem_id: str, req: UpdateTestFileRequest):
    try:
        update_test_file(problem_id, req.test_c)
        return {"status": "updated"}
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


# ---- Provider 管理 ----

@router.get("/providers")
async def list_providers():
    return await db.list_providers()


@router.post("/providers")
async def create_provider(req: CreateProviderRequest):
    if req.api_format not in ("openai", "anthropic"):
        raise HTTPException(400, "api_format 必须为 'openai' 或 'anthropic'")
    if not req.name.strip():
        raise HTTPException(400, "name 不能为空")
    if not req.api_key.strip():
        raise HTTPException(400, "api_key 不能为空")
    return await db.create_provider(
        name=req.name.strip(),
        api_format=req.api_format,
        api_key=req.api_key,
        base_url=req.base_url.strip(),
    )


@router.put("/providers/{provider_uuid}")
async def update_provider(provider_uuid: str, req: UpdateProviderRequest):
    existing = await db.get_provider(provider_uuid)
    if not existing:
        raise HTTPException(404, f"Provider '{provider_uuid}' not found")
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if "api_format" in kwargs and kwargs["api_format"] not in ("openai", "anthropic"):
        raise HTTPException(400, "api_format 必须为 'openai' 或 'anthropic'")
    ok = await db.update_provider(provider_uuid, **kwargs)
    if not ok:
        raise HTTPException(500, "Update failed")
    return {"status": "updated"}


@router.delete("/providers/{provider_uuid}")
async def delete_provider(provider_uuid: str):
    existing = await db.get_provider(provider_uuid)
    if not existing:
        raise HTTPException(404, f"Provider '{provider_uuid}' not found")
    # 检查该 provider 下是否有关联的 submissions
    conn = await db.get_db()
    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM submissions s JOIN models m ON s.model_uuid=m.uuid WHERE m.provider_uuid=?",
        (provider_uuid,)
    ) as cur:
        row = await cur.fetchone()
        if row and row["cnt"] > 0:
            raise HTTPException(400, f"该 provider 有 {row['cnt']} 条提交记录，无法删除")
    ok = await db.delete_provider(provider_uuid)
    if not ok:
        raise HTTPException(404, f"Provider '{provider_uuid}' not found")
    return {"status": "deleted"}


# ---- 模型管理 ----

@router.get("/models")
async def list_enabled_models():
    """获取所有已启用模型列表（用于评测选择）"""
    return await db.list_enabled_models()


@router.get("/model-configs")
async def list_model_configs():
    """获取所有模型配置（api_key 已掩码）"""
    return await db.list_model_configs()


@router.post("/model-configs")
async def create_model_config(req: CreateModelRequest):
    provider = await db.get_provider(req.provider_uuid)
    if not provider:
        raise HTTPException(404, f"Provider '{req.provider_uuid}' not found")
    if not req.model_id.strip():
        raise HTTPException(400, "model_id 不能为空")
    return await db.create_model_config(
        provider_uuid=req.provider_uuid,
        model_id=req.model_id.strip(),
        thinking=req.thinking,
        thinking_budget=req.thinking_budget,
        max_tokens=req.max_tokens,
    )


@router.put("/model-configs/{model_uuid}")
async def update_model_config(model_uuid: str, req: UpdateModelRequest):
    existing = await db.get_model_config(model_uuid)
    if not existing:
        raise HTTPException(404, f"Model '{model_uuid}' not found")
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    ok = await db.update_model_config(model_uuid, **kwargs)
    if not ok:
        raise HTTPException(500, "Update failed")
    return {"status": "updated"}


@router.delete("/model-configs/{model_uuid}")
async def delete_model_config(model_uuid: str):
    ok = await db.delete_model_config(model_uuid)
    if not ok:
        raise HTTPException(404, f"Model '{model_uuid}' not found")
    return {"status": "deleted"}


@router.get("/model-stats/{model_uuid}")
async def model_stats(model_uuid: str):
    stats = await db.get_model_stats(model_uuid)
    if not stats:
        raise HTTPException(404, f"No data for model '{model_uuid}'")
    return stats


# ---- 评测轮次 ----

async def _get_providers():
    return await create_providers_from_db()


@router.post("/rounds")
async def create_round(req: CreateRoundRequest, background_tasks: BackgroundTasks):
    all_problems = await db.list_problems_db()
    all_ids = {p["id"] for p in all_problems}
    problem_ids = req.problem_ids or list(all_ids)
    valid_problems = [pid for pid in problem_ids if pid in all_ids]
    if not valid_problems:
        raise HTTPException(400, "No valid problems found")

    providers = await _get_providers()
    model_uuids = req.model_uuids or list(providers.keys())
    valid_models = [m for m in model_uuids if m in providers]
    if not valid_models:
        raise HTTPException(400, "No models configured")

    import uuid as _uuid
    round_id = f"round-{_uuid.uuid4().hex[:8]}"
    await db.create_round(round_id, valid_problems, valid_models, req.name)
    await db.update_round_status(round_id, "running")

    async def _run():
        await run_benchmark(valid_problems, valid_models, providers, req.name, round_id=round_id)

    background_tasks.add_task(_run)

    return {
        "status": "started",
        "round_id": round_id,
        "problems": valid_problems,
        "models": valid_models,
        "total_tasks": len(valid_problems) * len(valid_models),
        "message": f"Round created. Use GET /api/rounds/{round_id} to track progress.",
    }


@router.post("/rounds/sync")
async def create_round_sync(req: CreateRoundRequest):
    all_problems = await db.list_problems_db()
    all_ids = {p["id"] for p in all_problems}
    problem_ids = req.problem_ids or list(all_ids)
    valid_problems = [pid for pid in problem_ids if pid in all_ids]
    if not valid_problems:
        raise HTTPException(400, "No valid problems found")

    providers = await _get_providers()
    model_uuids = req.model_uuids or list(providers.keys())
    valid_models = [m for m in model_uuids if m in providers]
    if not valid_models:
        raise HTTPException(400, "No models configured")

    round_id = await run_benchmark(valid_problems, valid_models, providers, req.name)

    round_data = await db.get_round(round_id)
    submissions = await db.get_submissions_by_round(round_id)
    leaderboard = await db.get_leaderboard(round_id)

    return {"round": round_data, "leaderboard": leaderboard, "submissions": submissions}


@router.get("/rounds")
async def get_rounds():
    rounds = await db.list_rounds()
    round_ids = [r["id"] for r in rounds]
    leaderboards = await db.get_leaderboards_for_rounds(round_ids)
    for r in rounds:
        r["leaderboard"] = leaderboards.get(r["id"], [])
    return rounds


@router.get("/rounds/{round_id}/progress")
async def get_round_progress(round_id: str):
    round_data = await db.get_round(round_id)
    if not round_data:
        raise HTTPException(404, f"Round '{round_id}' not found")
    progress = await db.get_round_progress(round_id)
    return {"round_status": round_data["status"], "submissions": progress}


@router.get("/rounds/{round_id}")
async def get_round(round_id: str):
    round_data = await db.get_round(round_id)
    if not round_data:
        raise HTTPException(404, f"Round '{round_id}' not found")
    submissions = await db.get_submissions_by_round(round_id)
    leaderboard = await db.get_leaderboard(round_id)
    return {"round": round_data, "leaderboard": leaderboard, "submissions": submissions}


# ---- 结果 ----

@router.get("/leaderboard/{round_id}")
async def get_leaderboard(round_id: str):
    round_data = await db.get_round(round_id)
    if not round_data:
        raise HTTPException(404, f"Round '{round_id}' not found")
    return await db.get_leaderboard(round_id)


@router.get("/submissions/{round_id}/{problem_id}/{model_uuid}")
async def get_submission(round_id: str, problem_id: str, model_uuid: str):
    sub = await db.get_submission(round_id, problem_id, model_uuid)
    if not sub:
        raise HTTPException(404, "Submission not found")
    return sub
