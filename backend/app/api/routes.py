"""
AICoderBench API 路由
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from pydantic import BaseModel

from ..models.problem import list_problems, load_problem, create_problem, update_problem, delete_problem, update_test_file
from ..providers.model_provider import create_providers_from_db
from ..scheduler.engine import run_benchmark
from .. import database as db

router = APIRouter()


# ---- Pydantic 模型 ----

class CreateRoundRequest(BaseModel):
    name: str = ""
    problem_ids: Optional[list[str]] = None
    model_uuids: Optional[list[str]] = None


class CreateModelRequest(BaseModel):
    provider: str  # glm / kimi / minimax / openrouter
    api_model: str  # API 模型名
    api_key: str
    base_url: str = ""
    thinking: bool = False


class UpdateModelRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    thinking: Optional[bool] = None
    enabled: Optional[bool] = None


class CreateProblemRequest(BaseModel):
    id: str
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


# ---- 辅助 ----

async def _get_providers():
    """
    从数据库加载启用的模型 provider。
    返回 dict：key = model_uuid, value = ModelProvider 实例
    """
    return await create_providers_from_db()


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
    return list_problems()


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: str):
    try:
        return load_problem(problem_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.post("/problems")
async def create_problem_api(req: CreateProblemRequest):
    """创建新题目"""
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', req.id):
        raise HTTPException(400, "ID 只能包含字母、数字、下划线和连字符")
    if not req.title.strip():
        raise HTTPException(400, "标题不能为空")
    try:
        return create_problem(
            id=req.id,
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
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@router.put("/problems/{problem_id}")
async def update_problem_api(problem_id: str, req: UpdateProblemRequest):
    """更新题目"""
    try:
        return update_problem(
            problem_id=problem_id,
            **{k: v for k, v in req.model_dump().items() if v is not None},
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.delete("/problems/{problem_id}")
async def delete_problem_api(problem_id: str):
    """删除题目"""
    # 检查是否有 submissions 引用
    conn = await db.get_db()
    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM submissions WHERE problem_id=?", (problem_id,)
    ) as cur:
        row = await cur.fetchone()
        if row and row["cnt"] > 0:
            raise HTTPException(400, f"该题目有 {row['cnt']} 条提交记录，无法删除")
    try:
        delete_problem(problem_id)
        return {"status": "deleted"}
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.post("/problems/{problem_id}/test-file")
async def upload_test_file(problem_id: str, req: UpdateTestFileRequest):
    """上传/更新测试文件"""
    try:
        update_test_file(problem_id, req.test_c)
        return {"status": "updated"}
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


# ---- 模型 ----

@router.get("/models")
async def get_models():
    """获取所有已启用模型列表（用于评测选择）"""
    conn = await db.get_db()
    async with conn.execute("SELECT uuid, provider, model, thinking FROM models WHERE enabled=1") as cur:
        rows = await cur.fetchall()
    return [
        {
            "uuid": row["uuid"],
            "provider": row["provider"],
            "api_model": row["model"],
            "thinking": bool(row["thinking"]),
        }
        for row in rows
    ]


# ---- 模型管理 ----

@router.get("/model-configs")
async def list_model_configs():
    """获取所有模型配置（api_key 已掩码）"""
    return await db.list_model_configs()


@router.post("/model-configs")
async def create_model_config(req: CreateModelRequest):
    """添加新模型"""
    valid_providers = ["glm", "kimi", "minimax", "openrouter"]
    if req.provider not in valid_providers:
        raise HTTPException(400, f"Invalid provider, must be one of: {valid_providers}")

    existing = await db.get_model_by_provider_model(req.provider, req.api_model, req.thinking)
    if existing:
        raise HTTPException(400, f"Model with provider={req.provider}, api_model={req.api_model}, thinking={req.thinking} already exists")

    return await db.create_model_config(
        provider=req.provider,
        model=req.api_model,
        api_key=req.api_key,
        base_url=req.base_url,
        thinking=req.thinking,
    )


@router.put("/model-configs/{uuid}")
async def update_model_config(uuid: str, req: UpdateModelRequest):
    """更新模型配置"""
    existing = await db.get_model_config(uuid)
    if not existing:
        raise HTTPException(404, f"Model '{uuid}' not found")
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(400, "No fields to update")
    ok = await db.update_model_config(uuid, **kwargs)
    if not ok:
        raise HTTPException(500, "Update failed")
    return {"status": "updated"}


@router.delete("/model-configs/{uuid}")
async def delete_model_config(uuid: str):
    """删除模型"""
    ok = await db.delete_model_config(uuid)
    if not ok:
        raise HTTPException(404, f"Model '{uuid}' not found")
    return {"status": "deleted"}


@router.get("/model-stats/{model_uuid}")
async def model_stats(model_uuid: str):
    stats = await db.get_model_stats(model_uuid)
    if not stats:
        raise HTTPException(404, f"No data for model '{model_uuid}'")
    return stats


# ---- 评测轮次 ----

@router.post("/rounds")
async def create_round(req: CreateRoundRequest, background_tasks: BackgroundTasks):
    """创建并启动一轮评测（后台运行）"""
    all_problems = list_problems()
    problem_ids = req.problem_ids or [p.id for p in all_problems]
    valid_problems = [p.id for p in all_problems if p.id in problem_ids]
    if not valid_problems:
        raise HTTPException(400, "No valid problems found")

    providers = await _get_providers()
    model_uuids = req.model_uuids or list(providers.keys())
    valid_models = [m for m in model_uuids if m in providers]
    if not valid_models:
        raise HTTPException(400, "No models configured")

    async def _run():
        await run_benchmark(valid_problems, valid_models, providers, req.name)

    background_tasks.add_task(_run)

    return {
        "status": "started",
        "problems": valid_problems,
        "models": valid_models,
        "total_tasks": len(valid_problems) * len(valid_models),
        "message": "Round created. Use GET /api/rounds to track progress.",
    }


@router.post("/rounds/sync")
async def create_round_sync(req: CreateRoundRequest):
    """同步运行一轮评测（阻塞等待结果）"""
    all_problems = list_problems()
    problem_ids = req.problem_ids or [p.id for p in all_problems]
    valid_problems = [p.id for p in all_problems if p.id in problem_ids]
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

    return {
        "round": round_data,
        "leaderboard": leaderboard,
        "submissions": submissions,
    }


@router.get("/rounds")
async def get_rounds():
    rounds = await db.list_rounds()
    round_ids = [r["id"] for r in rounds]
    leaderboards = await db.get_leaderboards_for_rounds(round_ids)
    for r in rounds:
        r["leaderboard"] = leaderboards.get(r["id"], [])
    return rounds


@router.get("/rounds/{round_id}")
async def get_round(round_id: str):
    round_data = await db.get_round(round_id)
    if not round_data:
        raise HTTPException(404, f"Round '{round_id}' not found")

    submissions = await db.get_submissions_by_round(round_id)
    leaderboard = await db.get_leaderboard(round_id)

    return {
        "round": round_data,
        "leaderboard": leaderboard,
        "submissions": submissions,
    }


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
