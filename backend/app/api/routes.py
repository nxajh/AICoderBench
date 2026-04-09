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
    provider: str = "openai"   # 技术类型，目前统一使用 openai-compatible
    api_model: str             # API 调用时传的 model 参数
    api_key: str
    base_url: str = ""
    thinking: bool = False
    display_name: str = ""     # 显示名称，留空则自动推断


class UpdateModelRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    thinking: Optional[bool] = None
    enabled: Optional[bool] = None


class CreateProblemRequest(BaseModel):
    id: str = ""        # 留空则自动生成
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
    """列出所有题目（从数据库获取元数据，从文件获取内容）"""
    problems_meta = await db.list_problems_db()
    result = []
    for p in problems_meta:
        try:
            file_data = load_problem(p["slug"])
            result.append({**p, "description": file_data.description, "interface_h": file_data.interface_h})
        except FileNotFoundError:
            result.append(p)
    return result


@router.get("/problems/{problem_id}")
async def get_problem(problem_id: str):
    """获取单个题目。支持 uuid 或 slug"""
    # 先尝试 uuid
    p = await db.get_problem_by_uuid(problem_id)
    if not p:
        # 再尝试 slug
        p = await db.get_problem_by_slug(problem_id)
    if not p:
        raise HTTPException(404, f"Problem '{problem_id}' not found")
    try:
        file_data = load_problem(p["slug"])
        return {**p, "description": file_data.description, "interface_h": file_data.interface_h}
    except FileNotFoundError:
        return p


@router.post("/problems")
async def create_problem_api(req: CreateProblemRequest):
    """创建新题目"""
    import re, uuid as _uuid
    if not req.title.strip():
        raise HTTPException(400, "标题不能为空")

    # 自动生成 ID：按现有题目数量定序号，加随机短码避免冲突
    problem_id = req.id.strip()
    if not problem_id:
        from ..config import PROBLEMS_DIR
        existing = [d for d in PROBLEMS_DIR.iterdir() if d.is_dir() and (d / "problem.json").exists()] if PROBLEMS_DIR.exists() else []
        next_num = len(existing) + 1
        problem_id = f"{next_num:02d}-{_uuid.uuid4().hex[:6]}"
    elif not re.match(r'^[a-zA-Z0-9_-]+$', problem_id):
        raise HTTPException(400, "ID 只能包含字母、数字、下划线和连字符")

    if req.scoring:
        weight_total = sum(v for v in req.scoring.values() if isinstance(v, (int, float)))
        if weight_total != 100:
            raise HTTPException(400, f"scoring 权重之和须为 100，当前为 {weight_total}")
    try:
        prob = create_problem(
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
        # 文件已写入，同步到数据库（权威来源是文件）
        await db.sync_problems_from_disk()
        # 返回带 uuid 的版本
        p = await db.get_problem_by_slug(problem_id)
        return p if p else prob.model_dump()
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@router.put("/problems/{problem_id}")
async def update_problem_api(problem_id: str, req: UpdateProblemRequest):
    """更新题目（文件是权威来源，写文件后同步数据库）"""
    if req.scoring is not None:
        weight_total = sum(v for v in req.scoring.values() if isinstance(v, (int, float)))
        if weight_total != 100:
            raise HTTPException(400, f"scoring 权重之和须为 100，当前为 {weight_total}")
    slug = problem_id
    p = await db.get_problem_by_uuid(problem_id)
    if p:
        slug = p["slug"]
    try:
        updated = update_problem(
            problem_id=slug,
            **{k: v for k, v in req.model_dump().items() if v is not None},
        )
        # 文件已更新，全量同步到数据库
        await db.sync_problems_from_disk()
        # 返回带 uuid 的版本
        fresh = await db.get_problem_by_slug(slug)
        if fresh:
            return {**fresh, "description": updated.description, "interface_h": updated.interface_h}
        return updated.model_dump()
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.delete("/problems/{problem_id}")
async def delete_problem_api(problem_id: str):
    """删除题目"""
    slug = problem_id
    p = await db.get_problem_by_uuid(problem_id)
    if p:
        slug = p["slug"]
    # 检查是否有 submissions 引用
    conn = await db.get_db()
    check_id = p["uuid"] if p else problem_id
    async with conn.execute(
        "SELECT COUNT(*) as cnt FROM submissions WHERE problem_id=?", (check_id,)
    ) as cur:
        row = await cur.fetchone()
        if row and row["cnt"] > 0:
            raise HTTPException(400, f"该题目有 {row['cnt']} 条提交记录，无法删除")
    try:
        delete_problem(slug)
        # 从数据库也删除
        if p:
            await conn.execute("DELETE FROM problems WHERE uuid=?", (p["uuid"],))
            await conn.commit()
        return {"status": "deleted"}
    except FileNotFoundError:
        raise HTTPException(404, f"Problem '{problem_id}' not found")


@router.post("/problems/{problem_id}/test-file")
async def upload_test_file(problem_id: str, req: UpdateTestFileRequest):
    """上传/更新测试文件"""
    slug = problem_id
    p = await db.get_problem_by_uuid(problem_id)
    if p:
        slug = p["slug"]
    try:
        update_test_file(slug, req.test_c)
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
    existing = await db.get_model_by_provider_model(req.provider, req.api_model, req.thinking)
    if existing:
        raise HTTPException(400, f"Model with provider={req.provider}, api_model={req.api_model}, thinking={req.thinking} already exists")

    return await db.create_model_config(
        provider_type=req.provider,
        display_name=req.display_name,
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
    all_problems = await db.list_problems_db()
    all_uuids = {p["uuid"] for p in all_problems}
    problem_ids = req.problem_ids or list(all_uuids)
    valid_problems = [pid for pid in problem_ids if pid in all_uuids]
    if not valid_problems:
        raise HTTPException(400, "No valid problems found")

    providers = await _get_providers()
    model_uuids = req.model_uuids or list(providers.keys())
    valid_models = [m for m in model_uuids if m in providers]
    if not valid_models:
        raise HTTPException(400, "No models configured")

    # 提前生成 round_id，以便立即返回给客户端用于追踪进度
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
    """同步运行一轮评测（阻塞等待结果）"""
    all_problems = await db.list_problems_db()
    all_uuids = {p["uuid"] for p in all_problems}
    problem_ids = req.problem_ids or list(all_uuids)
    valid_problems = [pid for pid in problem_ids if pid in all_uuids]
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


@router.get("/rounds/{round_id}/progress")
async def get_round_progress(round_id: str):
    """轻量级进度接口，仅返回每个 submission 的状态和当前 agent 轮次，供前端高频轮询"""
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
