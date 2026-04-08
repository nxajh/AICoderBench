"""
SQLite 数据库层
"""
import json
import aiosqlite
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from .config import DATABASE_URL


DB_PATH = DATABASE_URL.replace("sqlite:///", "")

# 模块级共享连接
_db: Optional[aiosqlite.Connection] = None

# 列名白名单
VALID_SUBMISSION_COLUMNS = {
    "status", "generated_code", "raw_output", "used_tool_call",
    "generation_error", "eval_result", "total_score", "score_breakdown",
    "created_at", "finished_at", "generation_duration", "token_usage",
    "model_uuid", "model_id", "prompt",
}

VALID_MODEL_COLUMNS = {
    "api_key", "base_url", "thinking", "enabled", "provider", "model",
    "provider_type", "name",
}


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
    return _db


async def init_db():
    """初始化数据库表"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            difficulty TEXT DEFAULT 'medium',
            language TEXT DEFAULT 'c',
            tags TEXT DEFAULT '[]',
            compile_flags TEXT DEFAULT '',
            timeout_seconds INTEGER DEFAULT 30,
            scoring TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS models (
            uuid TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            thinking INTEGER DEFAULT 0,
            name TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            base_url TEXT DEFAULT '',
            provider_type TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            problem_ids TEXT DEFAULT '[]',
            model_uuids TEXT DEFAULT '[]',
            created_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            model_uuid TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            prompt TEXT DEFAULT '',
            generated_code TEXT DEFAULT '',
            raw_output TEXT DEFAULT '',
            used_tool_call INTEGER DEFAULT 0,
            generation_error TEXT DEFAULT '',
            eval_result TEXT DEFAULT '{}',
            total_score INTEGER DEFAULT 0,
            score_breakdown TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT '',
            generation_duration REAL DEFAULT 0,
            token_usage TEXT DEFAULT '{}',
            UNIQUE(round_id, problem_id, model_uuid)
        );

        CREATE INDEX IF NOT EXISTS idx_submissions_round ON submissions(round_id);
        CREATE INDEX IF NOT EXISTS idx_submissions_model ON submissions(model_uuid);
    """)

    # 迁移：添加 generation_duration 字段（如果不存在）
    cursor = await db.execute("PRAGMA table_info(submissions)")
    columns = [row[1] for row in await cursor.fetchall()]
    if "generation_duration" not in columns:
        await db.execute("ALTER TABLE submissions ADD COLUMN generation_duration REAL DEFAULT 0")
    if "token_usage" not in columns:
        await db.execute("ALTER TABLE submissions ADD COLUMN token_usage TEXT DEFAULT '{}'")
    if "model_uuid" not in columns:
        await db.execute("ALTER TABLE submissions ADD COLUMN model_uuid TEXT DEFAULT ''")

    # 迁移：rounds 表 model_ids → model_uuids
    cursor = await db.execute("PRAGMA table_info(rounds)")
    round_columns = [row[1] for row in await cursor.fetchall()]
    if "model_ids" in round_columns and "model_uuids" not in round_columns:
        await db.execute("ALTER TABLE rounds RENAME COLUMN model_ids TO model_uuids")

    # 迁移：submissions model_uuid 为空时用 model_id 填充
    await db.execute("UPDATE submissions SET model_uuid = model_id WHERE model_uuid = '' AND model_id != ''")

    # 迁移：扩展 models 表
    cursor = await db.execute("PRAGMA table_info(models)")
    model_columns = [row[1] for row in await cursor.fetchall()]
    if "api_key" not in model_columns:
        await db.execute("ALTER TABLE models ADD COLUMN api_key TEXT DEFAULT ''")
    if "base_url" not in model_columns:
        await db.execute("ALTER TABLE models ADD COLUMN base_url TEXT DEFAULT ''")
    if "provider_type" not in model_columns:
        await db.execute("ALTER TABLE models ADD COLUMN provider_type TEXT DEFAULT ''")
    if "enabled" not in model_columns:
        await db.execute("ALTER TABLE models ADD COLUMN enabled INTEGER DEFAULT 1")
    if "thinking" not in model_columns:
        await db.execute("ALTER TABLE models ADD COLUMN thinking INTEGER DEFAULT 0")
    if "uuid" not in model_columns:
        # 旧 schema 用 id 作主键，重命名为 uuid
        if "id" in model_columns:
            await db.execute("ALTER TABLE models RENAME COLUMN id TO uuid")

    await db.commit()


# ---- Round 操作 ----

async def create_round(round_id: str, problem_ids: list[str], model_uuids: list[str], name: str = "") -> dict:
    now = datetime.utcnow().isoformat()
    db = await get_db()
    await db.execute(
        "INSERT INTO rounds (id, name, status, problem_ids, model_uuids, created_at) VALUES (?, ?, 'pending', ?, ?, ?)",
        (round_id, name, json.dumps(problem_ids), json.dumps(model_uuids), now)
    )
    await db.commit()
    return {"id": round_id, "name": name, "status": "pending", "created_at": now}


async def update_round_status(round_id: str, status: str):
    now = datetime.utcnow().isoformat() if status in ("done", "failed") else ""
    db = await get_db()
    if now:
        await db.execute("UPDATE rounds SET status=?, finished_at=? WHERE id=?", (status, now, round_id))
    else:
        await db.execute("UPDATE rounds SET status=? WHERE id=?", (status, round_id))
    await db.commit()


async def delete_round(round_id: str):
    db = await get_db()
    await db.execute("DELETE FROM submissions WHERE round_id=?", (round_id,))
    await db.execute("DELETE FROM rounds WHERE id=?", (round_id,))
    await db.commit()


async def get_round(round_id: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM rounds WHERE id=?", (round_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["problem_ids"] = json.loads(d["problem_ids"])
        d["model_uuids"] = json.loads(d.get("model_uuids", "[]"))
        return d


async def list_rounds() -> list[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM rounds ORDER BY created_at DESC") as cursor:
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["problem_ids"] = json.loads(d["problem_ids"])
            d["model_uuids"] = json.loads(d.get("model_uuids", "[]"))
            result.append(d)
        return result


# ---- Submission 操作 ----

async def create_submission(round_id: str, problem_id: str, model_uuid: str) -> int:
    now = datetime.utcnow().isoformat()
    db = await get_db()
    cur = await db.execute(
        "SELECT id FROM submissions WHERE round_id=? AND problem_id=? AND model_uuid=?",
        (round_id, problem_id, model_uuid)
    )
    row = await cur.fetchone()
    await cur.close()
    if row:
        return row[0]
    cur = await db.execute(
        "INSERT INTO submissions (round_id, problem_id, model_id, model_uuid, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (round_id, problem_id, model_uuid, model_uuid, now)
    )
    await db.commit()
    return cur.lastrowid


async def update_submission(submission_id: int, **kwargs):
    if not kwargs:
        return
    invalid = set(kwargs.keys()) - VALID_SUBMISSION_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [submission_id]
    db = await get_db()
    await db.execute(f"UPDATE submissions SET {sets} WHERE id=?", values)
    await db.commit()


async def get_submissions_by_round(round_id: str) -> list[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM submissions WHERE round_id=? ORDER BY problem_id, model_uuid",
        (round_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("eval_result"):
                d["eval_result"] = json.loads(d["eval_result"])
            if d.get("score_breakdown"):
                d["score_breakdown"] = json.loads(d["score_breakdown"])
            d["used_tool_call"] = bool(d.get("used_tool_call", 0))
            result.append(d)
        return result



def _clean_thinking(text: str) -> str:
    """去除思考内容的标记标签"""
    import re as _re
    # 去掉开头的思考标记
    text = text.lstrip()
    text = _re.sub(r'^[​‌‍]*', '', text)
    text = _re.sub(r'^◀think▶\s*', '', text)
    text = _re.sub(r'^<think[^>]*>\s*', '', text)
    text = _re.sub(r'^ Pelosi\s*', '', text)  # zero-width space
    # 去掉结尾的闭合标签
    text = _re.sub(r'\s*◀/think▶\s*$', '', text)
    text = _re.sub(r'\s*</think\s*>\s*$', '', text)
    return text.strip()

async def get_submission(round_id: str, problem_id: str, model_uuid: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM submissions WHERE round_id=? AND problem_id=? AND model_uuid=?",
        (round_id, problem_id, model_uuid)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("prompt", None)
        # 解析 generation history
        if d.get("raw_output"):
            try:
                history = json.loads(d["raw_output"])
                # 对 history 做思考和输出分离
                for h in history:
                    # 旧格式：只有 text_preview
                    if "thinking" not in h and "text_preview" in h:
                        tp = h["text_preview"] or ""
                        if "</think" in tp:
                            idx = tp.find("</think")
                            end = tp.find(">", idx)
                            if end >= 0:
                                h["thinking"] = _clean_thinking(tp[:idx].strip())
                                h["output"] = tp[end+1:].strip()
                            else:
                                h["output"] = tp
                                h["thinking"] = ""
                        elif "\u200b" in tp[:5]:
                            h["thinking"] = _clean_thinking(tp)
                            h["output"] = ""
                        elif "\n\n\n" in tp:
                            parts = tp.split("\n\n\n", 1)
                            h["thinking"] = _clean_thinking(parts[0].strip())
                            h["output"] = parts[1].strip()
                        else:
                            h["output"] = tp
                            h["thinking"] = ""
                    # 中间格式：有 thinking 但包含 </think（拆分不完整）
                    elif "thinking" in h and "</think" in (h.get("thinking") or ""):
                        combined = h["thinking"] or ""
                        idx = combined.find("</think")
                        end = combined.find(">", idx)
                        if end >= 0:
                            rest = combined[end+1:].strip()
                            if rest:
                                h["thinking"] = _clean_thinking(combined[:idx].strip())
                                h["output"] = rest
                d["generation_history"] = history
            except (json.JSONDecodeError, TypeError):
                d["generation_history"] = []
        else:
            d["generation_history"] = []
        d.pop("raw_output", None)
        if d.get("eval_result"):
            d["eval_result"] = json.loads(d["eval_result"])
        if d.get("score_breakdown"):
            d["score_breakdown"] = json.loads(d["score_breakdown"])
        d["used_tool_call"] = bool(d.get("used_tool_call", 0))
        if d.get("token_usage") and isinstance(d["token_usage"], str):
            d["token_usage"] = json.loads(d["token_usage"])
    # 附上 model 元信息
    async with db.execute(
        "SELECT provider, model, thinking FROM models WHERE uuid=?", (model_uuid,)
    ) as cur:
        minfo = await cur.fetchone()
        if minfo:
            d["model_provider"] = minfo["provider"]
            d["model_name"] = minfo["model"]
            d["model_thinking"] = bool(minfo["thinking"])
    return d


# ---- Global Leaderboard ----

async def get_global_leaderboard() -> list[dict]:
    """跨所有 rounds 聚合的模型排行榜"""
    db = await get_db()
    async with db.execute("""
        SELECT model_uuid,
               problem_id,
               MAX(total_score) as best_score,
               COUNT(*) as sub_count
        FROM submissions
        WHERE status='done'
        GROUP BY model_uuid, problem_id
    """) as cursor:
        problem_rows = await cursor.fetchall()

    # 获取每个模型的总 token 用量
    token_data: dict = {}
    async with db.execute("""
        SELECT model_uuid,
               SUM(CASE WHEN token_usage IS NOT NULL AND token_usage != '' AND token_usage != '{}'
                   THEN json_extract(token_usage, '$.total_tokens') ELSE 0 END) as total_tokens
        FROM submissions
        WHERE status='done'
        GROUP BY model_uuid
    """) as cur:
        for r in await cur.fetchall():
            token_data[r["model_uuid"]] = r["total_tokens"] or 0

    model_data: dict = {}
    for row in problem_rows:
        muuid = row["model_uuid"]
        if muuid not in model_data:
            model_data[muuid] = {"total_score": 0, "problems": [], "total_subs": 0}
        model_data[muuid]["total_score"] += row["best_score"]
        model_data[muuid]["problems"].append(row["best_score"])
        model_data[muuid]["total_subs"] += row["sub_count"]

    model_info: dict = {}
    async with db.execute("SELECT uuid, provider, model, thinking FROM models") as cur:
        for r in await cur.fetchall():
            model_info[r["uuid"]] = dict(r)

    result = []
    for muuid, d in model_data.items():
        probs = d["problems"]
        n = len(probs)
        win_count = sum(1 for s in probs if s >= 80)
        info = model_info.get(muuid, {})
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider", ""),
            "model": info.get("model", ""),
            "thinking": bool(info.get("thinking", 0)),
            "total_score": d["total_score"],
            "problems_attempted": n,
            "avg_score": round(sum(probs) / n, 1) if n else 0,
            "win_rate": round(win_count / n * 100, 1) if n else 0,
            "total_submissions": d["total_subs"],
            "total_tokens": token_data.get(muuid, 0),
        })

    result.sort(key=lambda x: x["total_score"], reverse=True)
    return result


async def get_model_stats(model_uuid: str) -> Optional[dict]:
    """获取某个模型在各题目上的详细统计"""
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM submissions WHERE model_uuid=?", (model_uuid,)
    ) as cur:
        count = (await cur.fetchone())[0]
    if count == 0:
        return None

    async with db.execute("SELECT uuid, provider, model, thinking FROM models WHERE uuid=?", (model_uuid,)) as cur:
        info = dict(await cur.fetchone())

    async with db.execute("SELECT id, title FROM problems") as cur:
        title_map = {r["id"]: r["title"] async for r in cur}

    async with db.execute("""
        SELECT problem_id,
               MAX(total_score) as best_score,
               MIN(total_score) as worst_score,
               AVG(total_score) as avg_score,
               COUNT(*) as submission_count
        FROM submissions
        WHERE model_uuid=? AND status='done'
        GROUP BY problem_id
        ORDER BY problem_id
    """, (model_uuid,)) as cursor:
        rows = await cursor.fetchall()

    problems = []
    for row in rows:
        pid = row["problem_id"]
        async with db.execute("""
            SELECT token_usage FROM submissions
            WHERE model_uuid=? AND problem_id=? AND status='done'
        """, (model_uuid, pid)) as tcur:
            token_rows = await tcur.fetchall()

        avg_tokens = {"prompt": 0, "completion": 0, "total": 0}
        valid_count = 0
        for tr in token_rows:
            try:
                tu = json.loads(tr["token_usage"]) if tr["token_usage"] else {}
                if tu:
                    avg_tokens["prompt"] += tu.get("prompt_tokens", tu.get("prompt", 0))
                    avg_tokens["completion"] += tu.get("completion_tokens", tu.get("completion", 0))
                    avg_tokens["total"] += tu.get("total_tokens", tu.get("total", 0))
                    valid_count += 1
            except (json.JSONDecodeError, TypeError):
                pass
        if valid_count > 0:
            avg_tokens = {k: round(v / valid_count) for k, v in avg_tokens.items()}

        problems.append({
            "problem_id": pid,
            "title": title_map.get(pid, pid),
            "best_score": row["best_score"],
            "worst_score": row["worst_score"],
            "avg_score": round(row["avg_score"], 1),
            "submission_count": row["submission_count"],
            "avg_tokens": avg_tokens,
        })

    return {
        "model_uuid": model_uuid,
        "provider": info.get("provider", ""),
        "model": info.get("model", ""),
        "thinking": bool(info.get("thinking", 0)),
        "problems": problems,
    }


# ---- Leaderboard ----

async def get_leaderboard(round_id: str) -> list[dict]:
    """按模型汇总分数，返回排行榜"""
    db = await get_db()
    async with db.execute(
        """SELECT model_uuid,
                  COUNT(*) as total_problems,
                  SUM(total_score) as total_score,
                  SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as completed,
                  AVG(total_score) as avg_score
           FROM submissions WHERE round_id=?
           GROUP BY model_uuid ORDER BY total_score DESC""",
        (round_id,)
    ) as cursor:
        rows = await cursor.fetchall()

    model_info: dict = {}
    async with db.execute("SELECT uuid, provider, model, thinking FROM models") as cur:
        for r in await cur.fetchall():
            model_info[r["uuid"]] = dict(r)

    result = []
    for row in rows:
        muuid = row["model_uuid"]
        info = model_info.get(muuid, {})
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider", ""),
            "model": info.get("model", ""),
            "thinking": bool(info.get("thinking", 0)),
            "total_problems": row["total_problems"],
            "total_score": row["total_score"] or 0,
            "completed": row["completed"],
            "avg_score": round(row["avg_score"] or 0, 1),
        })
    return result


async def get_leaderboards_for_rounds(round_ids: list[str]) -> dict[str, list[dict]]:
    """批量获取多个 round 的排行榜"""
    if not round_ids:
        return {}
    db = await get_db()
    placeholders = ",".join("?" for _ in round_ids)
    async with db.execute(
        f"""SELECT model_uuid, round_id,
                  COUNT(*) as total_problems,
                  SUM(total_score) as total_score,
                  SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as completed,
                  AVG(total_score) as avg_score
           FROM submissions WHERE round_id IN ({placeholders})
           GROUP BY round_id, model_uuid
           ORDER BY round_id, total_score DESC""",
        round_ids
    ) as cursor:
        rows = await cursor.fetchall()

    model_info: dict = {}
    async with db.execute("SELECT uuid, provider, model, thinking FROM models") as cur:
        for r in await cur.fetchall():
            model_info[r["uuid"]] = dict(r)

    result: dict[str, list[dict]] = {rid: [] for rid in round_ids}
    for row in rows:
        muuid = row["model_uuid"]
        rid = row["round_id"]
        info = model_info.get(muuid, {})
        result[rid].append({
            "model_uuid": muuid,
            "provider": info.get("provider", ""),
            "model": info.get("model", ""),
            "thinking": bool(info.get("thinking", 0)),
            "total_problems": row["total_problems"],
            "total_score": row["total_score"] or 0,
            "completed": row["completed"],
            "avg_score": round(row["avg_score"] or 0, 1),
        })
    return result


async def get_problem_leaderboard(problem_id: str, limit: int = 10) -> list[dict]:
    """获取某题目的模型排行榜（按最高分排序），附带最佳提交的 round_id 和 token"""
    db = await get_db()
    async with db.execute("""
        SELECT model_uuid,
               MAX(total_score) as best_score,
               AVG(total_score) as avg_score,
               COUNT(*) as submissions
        FROM submissions
        WHERE problem_id=? AND status='done'
        GROUP BY model_uuid
        ORDER BY best_score DESC
        LIMIT ?
    """, (problem_id, limit)) as cursor:
        rows = await cursor.fetchall()

    model_info: dict = {}
    async with db.execute("SELECT uuid, provider, model, thinking FROM models") as cur:
        for r in await cur.fetchall():
            model_info[r["uuid"]] = dict(r)

    result = []
    for row in rows:
        muuid = row["model_uuid"]
        info = model_info.get(muuid, {})
        # 查找该模型在该题的最佳提交的 round_id、token、耗时、轮次
        best_round_id = ""
        best_tokens = 0
        best_duration = 0.0
        best_rounds = 0
        async with db.execute(
            "SELECT round_id, token_usage, generation_duration, raw_output FROM submissions WHERE model_uuid=? AND problem_id=? AND status='done' ORDER BY total_score DESC LIMIT 1",
            (muuid, problem_id)
        ) as bcur:
            brow = await bcur.fetchone()
            if brow:
                best_round_id = brow["round_id"]
                tu = brow["token_usage"]
                if tu:
                    try:
                        best_tokens = json.loads(tu).get("total_tokens", 0)
                    except (json.JSONDecodeError, TypeError):
                        pass
                best_duration = brow["generation_duration"] or 0
                raw = brow["raw_output"]
                if raw:
                    try:
                        best_rounds = len(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider", ""),
            "model": info.get("model", ""),
            "thinking": bool(info.get("thinking", 0)),
            "best_score": row["best_score"],
            "total_tokens": best_tokens,
            "duration": round(best_duration, 1),
            "rounds": best_rounds,
            "best_round_id": best_round_id,
        })
    return result


# ---- Model 管理 ----

async def list_model_configs() -> list[dict]:
    """返回所有模型配置（api_key 掩码处理）"""
    db = await get_db()
    async with db.execute("SELECT * FROM models ORDER BY provider, model") as cursor:
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["api_key_masked"] = _mask_key(d.get("api_key", ""))
            d.pop("api_key", None)
            d.pop("name", None)
            d["enabled"] = bool(d.get("enabled", 1))
            d["thinking"] = bool(d.get("thinking", 0))
            result.append(d)
        return result


async def get_model_config(uuid: str) -> Optional[dict]:
    """获取模型完整配置（含 api_key，仅内部使用）"""
    db = await get_db()
    async with db.execute("SELECT * FROM models WHERE uuid=?", (uuid,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["enabled"] = bool(d.get("enabled", 1))
        d["thinking"] = bool(d.get("thinking", 0))
        d.pop("name", None)
        d.pop("provider_type", None)
        return d


async def get_model_by_provider_model(provider: str, model: str, thinking: bool) -> Optional[dict]:
    """根据 provider + model + thinking 查找模型"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM models WHERE provider=? AND model=? AND thinking=?",
        (provider, model, int(thinking))
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["enabled"] = bool(d.get("enabled", 1))
        d["thinking"] = bool(d.get("thinking", 0))
        d.pop("name", None)
        d.pop("provider_type", None)
        return d


async def create_model_config(
    provider: str, model: str, api_key: str, base_url: str = "",
    thinking: bool = False,
) -> dict:
    """创建模型配置，自动生成 UUID"""
    new_uuid = str(uuid.uuid4())
    db = await get_db()
    await db.execute(
        "INSERT INTO models (uuid, provider, model, thinking, api_key, base_url, provider_type, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (new_uuid, provider, model, int(thinking), api_key, base_url, provider)
    )
    await db.commit()
    return {"uuid": new_uuid}


async def update_model_config(uuid: str, **kwargs) -> bool:
    """更新模型配置。api_key 为空则保留原值。"""
    if not kwargs:
        return False

    invalid = set(kwargs.keys()) - VALID_MODEL_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")

    existing = await get_model_config(uuid)
    if not existing:
        return False

    if "api_key" in kwargs and not kwargs["api_key"]:
        del kwargs["api_key"]
    if "thinking" in kwargs:
        kwargs["thinking"] = int(kwargs["thinking"])
    if "enabled" in kwargs:
        kwargs["enabled"] = int(kwargs["enabled"])
    kwargs.pop("provider_type", None)
    kwargs.pop("model", None)

    if not kwargs:
        return True

    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [uuid]
    db = await get_db()
    cursor = await db.execute(f"UPDATE models SET {sets} WHERE uuid=?", values)
    await db.commit()
    return cursor.rowcount > 0


async def delete_model_config(uuid: str) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM models WHERE uuid=?", (uuid,))
    await db.commit()
    return cursor.rowcount > 0


def _mask_key(key: str) -> str:
    """掩码 API key，只显示前4位和后4位"""
    if not key or len(key) < 12:
        return "****" if key else ""
    return f"{key[:4]}...{key[-4:]}"
