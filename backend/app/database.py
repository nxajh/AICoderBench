"""
SQLite 数据库层
"""
import json
import logging
import aiosqlite
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from .config import DATABASE_URL

DB_PATH = DATABASE_URL.replace("sqlite:///", "")

_db: Optional[aiosqlite.Connection] = None

VALID_SUBMISSION_COLUMNS = {
    "status", "generated_code", "used_tool_call",
    "generation_error", "eval_result", "total_score", "score_breakdown",
    "created_at", "finished_at", "generation_duration", "token_usage",
    "agent_round", "generation_history",
}

VALID_MODEL_COLUMNS = {
    "model_id", "thinking", "thinking_budget", "enabled", "max_tokens",
}

VALID_PROVIDER_COLUMNS = {
    "name", "api_format", "api_key", "base_url",
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
            id               TEXT PRIMARY KEY,
            title            TEXT NOT NULL,
            difficulty       TEXT DEFAULT 'medium',
            language         TEXT DEFAULT 'c',
            tags             TEXT DEFAULT '[]',
            compile_flags    TEXT DEFAULT '',
            timeout_seconds  INTEGER DEFAULT 30,
            concurrent       INTEGER DEFAULT 1,
            perf_baseline_ms INTEGER DEFAULT 0,
            scoring          TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS providers (
            uuid        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            api_format  TEXT NOT NULL DEFAULT 'openai',
            api_key     TEXT NOT NULL,
            base_url    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS models (
            uuid            TEXT PRIMARY KEY,
            provider_uuid   TEXT NOT NULL REFERENCES providers(uuid),
            model_id        TEXT NOT NULL,
            thinking        INTEGER DEFAULT 0,
            thinking_budget INTEGER DEFAULT 10000,
            enabled         INTEGER DEFAULT 1,
            max_tokens      INTEGER DEFAULT 65536
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id          TEXT PRIMARY KEY,
            name        TEXT DEFAULT '',
            status      TEXT DEFAULT 'pending',
            problem_ids TEXT NOT NULL,
            model_uuids TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS submissions (
            round_id            TEXT NOT NULL REFERENCES rounds(id),
            problem_id          TEXT NOT NULL REFERENCES problems(id),
            model_uuid          TEXT NOT NULL REFERENCES models(uuid),
            status              TEXT DEFAULT 'pending',
            agent_round         INTEGER DEFAULT 0,
            used_tool_call      INTEGER DEFAULT 0,
            generated_code      TEXT DEFAULT '',
            generation_history  TEXT DEFAULT '[]',
            generation_duration REAL DEFAULT 0,
            token_usage         TEXT DEFAULT '{}',
            generation_error    TEXT DEFAULT '',
            eval_result         TEXT DEFAULT '{}',
            score_breakdown     TEXT DEFAULT '{}',
            total_score         INTEGER DEFAULT 0,
            created_at          TEXT NOT NULL,
            finished_at         TEXT,
            PRIMARY KEY (round_id, problem_id, model_uuid)
        );

        CREATE INDEX IF NOT EXISTS idx_sub_round   ON submissions(round_id);
        CREATE INDEX IF NOT EXISTS idx_sub_model   ON submissions(model_uuid);
        CREATE INDEX IF NOT EXISTS idx_sub_problem ON submissions(problem_id, status);
    """)

    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.commit()

    await sync_problems_from_disk()


# ---- 辅助 ----

def _mask_key(key: str) -> str:
    if not key or len(key) < 12:
        return "****" if key else ""
    return f"{key[:4]}...{key[-4:]}"


def _model_info_query() -> str:
    """返回 models JOIN providers 的公共 SELECT 片段"""
    return """
        SELECT m.uuid, m.model_id, m.thinking, m.thinking_budget, m.enabled, m.max_tokens,
               p.uuid as provider_uuid, p.name as provider_name, p.api_format
        FROM models m JOIN providers p ON m.provider_uuid = p.uuid
    """


# ---- Provider 操作 ----

async def list_providers() -> list[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM providers ORDER BY name") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["api_key_masked"] = _mask_key(d.get("api_key", ""))
        d.pop("api_key", None)
        result.append(d)
    return result


async def get_provider(provider_uuid: str) -> Optional[dict]:
    """获取 provider 完整信息（含 api_key，仅内部使用）"""
    db = await get_db()
    async with db.execute("SELECT * FROM providers WHERE uuid=?", (provider_uuid,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_provider(name: str, api_format: str, api_key: str, base_url: str = "") -> dict:
    new_uuid = str(uuid.uuid4())
    db = await get_db()
    await db.execute(
        "INSERT INTO providers (uuid, name, api_format, api_key, base_url) VALUES (?, ?, ?, ?, ?)",
        (new_uuid, name, api_format, api_key, base_url)
    )
    await db.commit()
    return {"uuid": new_uuid}


async def update_provider(provider_uuid: str, **kwargs) -> bool:
    invalid = set(kwargs.keys()) - VALID_PROVIDER_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    if "api_key" in kwargs and not kwargs["api_key"]:
        del kwargs["api_key"]
    if not kwargs:
        return True
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [provider_uuid]
    db = await get_db()
    cur = await db.execute(f"UPDATE providers SET {sets} WHERE uuid=?", values)
    await db.commit()
    return cur.rowcount > 0


async def delete_provider(provider_uuid: str) -> bool:
    db = await get_db()
    # 级联删除该 provider 下的所有 models
    await db.execute("DELETE FROM models WHERE provider_uuid=?", (provider_uuid,))
    cur = await db.execute("DELETE FROM providers WHERE uuid=?", (provider_uuid,))
    await db.commit()
    return cur.rowcount > 0


# ---- Model 操作 ----

async def list_model_configs() -> list[dict]:
    """返回所有模型配置（含 provider 信息，api_key 掩码）"""
    db = await get_db()
    async with db.execute(
        _model_info_query() + " ORDER BY p.name, m.model_id"
    ) as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["thinking"] = bool(d["thinking"])
        d["enabled"] = bool(d["enabled"])
        result.append(d)
    return result


async def get_model_config(model_uuid: str) -> Optional[dict]:
    """获取模型完整配置（含 provider api_key，仅内部使用）"""
    db = await get_db()
    async with db.execute(
        """SELECT m.uuid, m.model_id, m.thinking, m.thinking_budget, m.enabled, m.max_tokens,
                  p.uuid as provider_uuid, p.name as provider_name,
                  p.api_format, p.api_key, p.base_url
           FROM models m JOIN providers p ON m.provider_uuid = p.uuid
           WHERE m.uuid=?""",
        (model_uuid,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["thinking"] = bool(d["thinking"])
    d["enabled"] = bool(d["enabled"])
    return d


async def create_model_config(
    provider_uuid: str, model_id: str,
    thinking: bool = False, thinking_budget: int = 10000,
    enabled: bool = True, max_tokens: int = 65536,
) -> dict:
    new_uuid = str(uuid.uuid4())
    db = await get_db()
    await db.execute(
        """INSERT INTO models (uuid, provider_uuid, model_id, thinking, thinking_budget, enabled, max_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (new_uuid, provider_uuid, model_id, int(thinking), thinking_budget, int(enabled), max_tokens)
    )
    await db.commit()
    return {"uuid": new_uuid}


async def update_model_config(model_uuid: str, **kwargs) -> bool:
    invalid = set(kwargs.keys()) - VALID_MODEL_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    if "thinking" in kwargs:
        kwargs["thinking"] = int(kwargs["thinking"])
    if "enabled" in kwargs:
        kwargs["enabled"] = int(kwargs["enabled"])
    if not kwargs:
        return True
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [model_uuid]
    db = await get_db()
    cur = await db.execute(f"UPDATE models SET {sets} WHERE uuid=?", values)
    await db.commit()
    return cur.rowcount > 0


async def delete_model_config(model_uuid: str) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM models WHERE uuid=?", (model_uuid,))
    await db.commit()
    return cur.rowcount > 0


async def list_enabled_models() -> list[dict]:
    """获取所有已启用模型（含 provider 信息），用于评测选择"""
    db = await get_db()
    async with db.execute(
        _model_info_query() + " WHERE m.enabled=1 ORDER BY p.name, m.model_id"
    ) as cur:
        rows = await cur.fetchall()
    return [
        {
            "uuid": row["uuid"],
            "provider_name": row["provider_name"],
            "model_id": row["model_id"],
            "thinking": bool(row["thinking"]),
        }
        for row in rows
    ]


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
    db = await get_db()
    if status in ("done", "failed"):
        now = datetime.utcnow().isoformat()
        await db.execute("UPDATE rounds SET status=?, finished_at=? WHERE id=?", (status, now, round_id))
    else:
        await db.execute("UPDATE rounds SET status=? WHERE id=?", (status, round_id))
    await db.commit()


async def get_round(round_id: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM rounds WHERE id=?", (round_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["problem_ids"] = json.loads(d["problem_ids"])
    d["model_uuids"] = json.loads(d["model_uuids"])
    return d


async def list_rounds() -> list[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM rounds ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["problem_ids"] = json.loads(d["problem_ids"])
        d["model_uuids"] = json.loads(d["model_uuids"])
        result.append(d)
    return result


# ---- Submission 操作 ----

async def create_submission(round_id: str, problem_id: str, model_uuid: str):
    now = datetime.utcnow().isoformat()
    db = await get_db()
    await db.execute(
        """INSERT OR IGNORE INTO submissions
           (round_id, problem_id, model_uuid, status, created_at)
           VALUES (?, ?, ?, 'pending', ?)""",
        (round_id, problem_id, model_uuid, now)
    )
    await db.commit()


async def update_submission(round_id: str, problem_id: str, model_uuid: str, **kwargs):
    if not kwargs:
        return
    invalid = set(kwargs.keys()) - VALID_SUBMISSION_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [round_id, problem_id, model_uuid]
    db = await get_db()
    await db.execute(
        f"UPDATE submissions SET {sets} WHERE round_id=? AND problem_id=? AND model_uuid=?",
        values
    )
    await db.commit()


async def get_submission(round_id: str, problem_id: str, model_uuid: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM submissions WHERE round_id=? AND problem_id=? AND model_uuid=?",
        (round_id, problem_id, model_uuid)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["used_tool_call"] = bool(d.get("used_tool_call", 0))
    if d.get("generation_history"):
        try:
            d["generation_history"] = json.loads(d["generation_history"])
        except (json.JSONDecodeError, TypeError):
            d["generation_history"] = []
    else:
        d["generation_history"] = []
    if d.get("eval_result"):
        try:
            d["eval_result"] = json.loads(d["eval_result"])
        except (json.JSONDecodeError, TypeError):
            d["eval_result"] = {}
    if d.get("score_breakdown"):
        try:
            d["score_breakdown"] = json.loads(d["score_breakdown"])
        except (json.JSONDecodeError, TypeError):
            d["score_breakdown"] = {}
    if d.get("token_usage") and isinstance(d["token_usage"], str):
        try:
            d["token_usage"] = json.loads(d["token_usage"])
        except (json.JSONDecodeError, TypeError):
            d["token_usage"] = {}

    # 附上 model + provider 元信息
    cfg = await get_model_config(model_uuid)
    if cfg:
        d["model_name"] = cfg["model_id"]
        d["model_provider"] = cfg["provider_name"]
        d["model_thinking"] = cfg["thinking"]
    return d


async def get_submissions_by_round(round_id: str) -> list[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM submissions WHERE round_id=? ORDER BY problem_id, model_uuid",
        (round_id,)
    ) as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["used_tool_call"] = bool(d.get("used_tool_call", 0))
        if d.get("eval_result"):
            try:
                d["eval_result"] = json.loads(d["eval_result"])
            except (json.JSONDecodeError, TypeError):
                d["eval_result"] = {}
        if d.get("score_breakdown"):
            try:
                d["score_breakdown"] = json.loads(d["score_breakdown"])
            except (json.JSONDecodeError, TypeError):
                d["score_breakdown"] = {}
        result.append(d)
    return result


async def get_round_progress(round_id: str) -> list[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT model_uuid, problem_id, status, agent_round, total_score FROM submissions WHERE round_id=?",
        (round_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---- Leaderboard ----

async def _get_model_display_map() -> dict:
    """返回 {model_uuid: {provider_name, model_id, thinking}} 用于排行榜展示"""
    db = await get_db()
    async with db.execute(
        "SELECT m.uuid, m.model_id, m.thinking, p.name as provider_name FROM models m JOIN providers p ON m.provider_uuid=p.uuid"
    ) as cur:
        rows = await cur.fetchall()
    return {r["uuid"]: {"provider_name": r["provider_name"], "model_id": r["model_id"], "thinking": bool(r["thinking"])} for r in rows}


async def get_leaderboard(round_id: str) -> list[dict]:
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
    ) as cur:
        rows = await cur.fetchall()

    model_map = await _get_model_display_map()
    result = []
    for row in rows:
        muuid = row["model_uuid"]
        info = model_map.get(muuid, {})
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider_name", ""),
            "model": info.get("model_id", muuid[:8]),
            "thinking": info.get("thinking", False),
            "total_problems": row["total_problems"],
            "total_score": row["total_score"] or 0,
            "completed": row["completed"],
            "avg_score": round(row["avg_score"] or 0, 1),
        })
    return result


async def get_leaderboards_for_rounds(round_ids: list[str]) -> dict[str, list[dict]]:
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
           GROUP BY round_id, model_uuid ORDER BY round_id, total_score DESC""",
        round_ids
    ) as cur:
        rows = await cur.fetchall()

    model_map = await _get_model_display_map()
    result: dict[str, list[dict]] = {rid: [] for rid in round_ids}
    for row in rows:
        muuid = row["model_uuid"]
        rid = row["round_id"]
        info = model_map.get(muuid, {})
        result[rid].append({
            "model_uuid": muuid,
            "provider": info.get("provider_name", ""),
            "model": info.get("model_id", muuid[:8]),
            "thinking": info.get("thinking", False),
            "total_problems": row["total_problems"],
            "total_score": row["total_score"] or 0,
            "completed": row["completed"],
            "avg_score": round(row["avg_score"] or 0, 1),
        })
    return result


async def get_global_leaderboard() -> list[dict]:
    db = await get_db()
    async with db.execute("""
        SELECT model_uuid,
               problem_id,
               MAX(total_score) as best_score,
               COUNT(*) as sub_count
        FROM submissions
        WHERE status='done'
        GROUP BY model_uuid, problem_id
    """) as cur:
        problem_rows = await cur.fetchall()

    async with db.execute("""
        SELECT model_uuid,
               SUM(CASE WHEN token_usage IS NOT NULL AND token_usage != '' AND token_usage != '{}'
                   THEN json_extract(token_usage, '$.total_tokens') ELSE 0 END) as total_tokens
        FROM submissions WHERE status='done'
        GROUP BY model_uuid
    """) as cur:
        token_data = {r["model_uuid"]: r["total_tokens"] or 0 for r in await cur.fetchall()}

    model_data: dict = {}
    for row in problem_rows:
        muuid = row["model_uuid"]
        if muuid not in model_data:
            model_data[muuid] = {"total_score": 0, "problems": [], "total_subs": 0}
        model_data[muuid]["total_score"] += row["best_score"]
        model_data[muuid]["problems"].append(row["best_score"])
        model_data[muuid]["total_subs"] += row["sub_count"]

    model_map = await _get_model_display_map()
    result = []
    for muuid, d in model_data.items():
        probs = d["problems"]
        n = len(probs)
        win_count = sum(1 for s in probs if s >= 80)
        info = model_map.get(muuid, {})
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider_name", ""),
            "model": info.get("model_id", muuid[:8]),
            "thinking": info.get("thinking", False),
            "total_score": d["total_score"],
            "problems_attempted": n,
            "avg_score": round(sum(probs) / n, 1) if n else 0,
            "win_rate": round(win_count / n * 100, 1) if n else 0,
            "total_submissions": d["total_subs"],
            "total_tokens": token_data.get(muuid, 0),
        })
    result.sort(key=lambda x: x["total_score"], reverse=True)
    return result


async def get_problem_leaderboard(problem_id: str, limit: int = 10) -> list[dict]:
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
    """, (problem_id, limit)) as cur:
        rows = await cur.fetchall()

    model_map = await _get_model_display_map()

    if rows:
        model_uuids_str = ",".join("?" for _ in rows)
        async with db.execute(
            f"""
            SELECT model_uuid, round_id, token_usage, generation_duration, generation_history
            FROM (
                SELECT model_uuid, round_id, token_usage, generation_duration, generation_history,
                       ROW_NUMBER() OVER (PARTITION BY model_uuid ORDER BY total_score DESC) as rn
                FROM submissions
                WHERE problem_id=? AND status='done'
                  AND model_uuid IN ({model_uuids_str})
            ) WHERE rn = 1
            """,
            [problem_id] + [r["model_uuid"] for r in rows]
        ) as bcur:
            best_rows = {r["model_uuid"]: r for r in await bcur.fetchall()}
    else:
        best_rows = {}

    result = []
    for row in rows:
        muuid = row["model_uuid"]
        info = model_map.get(muuid, {})
        brow = best_rows.get(muuid)
        best_round_id = brow["round_id"] if brow else ""
        best_tokens, best_duration, best_rounds = 0, 0.0, 0
        if brow:
            tu = brow["token_usage"]
            if tu:
                try:
                    best_tokens = json.loads(tu).get("total_tokens", 0)
                except (json.JSONDecodeError, TypeError):
                    pass
            best_duration = brow["generation_duration"] or 0
            hist = brow["generation_history"]
            if hist:
                try:
                    best_rounds = len(json.loads(hist))
                except (json.JSONDecodeError, TypeError):
                    pass
        result.append({
            "model_uuid": muuid,
            "provider": info.get("provider_name", ""),
            "model": info.get("model_id", muuid[:8]),
            "thinking": info.get("thinking", False),
            "best_score": row["best_score"],
            "total_tokens": best_tokens,
            "duration": round(best_duration, 1),
            "rounds": best_rounds,
            "best_round_id": best_round_id,
        })
    return result


async def get_model_stats(model_uuid: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM submissions WHERE model_uuid=?", (model_uuid,)
    ) as cur:
        row = await cur.fetchone()
    if not row or row["cnt"] == 0:
        return None

    cfg = await get_model_config(model_uuid)
    if not cfg:
        return None

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
        GROUP BY problem_id ORDER BY problem_id
    """, (model_uuid,)) as cur:
        rows = await cur.fetchall()

    async with db.execute("""
        SELECT problem_id, token_usage
        FROM submissions
        WHERE model_uuid=? AND status='done' AND token_usage IS NOT NULL AND token_usage != '' AND token_usage != '{}'
    """, (model_uuid,)) as cur:
        all_token_rows = await cur.fetchall()

    token_sums: dict = {}
    for tr in all_token_rows:
        pid = tr["problem_id"]
        try:
            tu = json.loads(tr["token_usage"]) if tr["token_usage"] else {}
            if tu:
                if pid not in token_sums:
                    token_sums[pid] = {"prompt": 0, "completion": 0, "total": 0, "count": 0}
                token_sums[pid]["prompt"] += tu.get("prompt_tokens", tu.get("prompt", 0))
                token_sums[pid]["completion"] += tu.get("completion_tokens", tu.get("completion", 0))
                token_sums[pid]["total"] += tu.get("total_tokens", tu.get("total", 0))
                token_sums[pid]["count"] += 1
        except (json.JSONDecodeError, TypeError):
            pass

    problems = []
    for row in rows:
        pid = row["problem_id"]
        ts = token_sums.get(pid, {})
        n = ts.get("count", 0)
        avg_tokens = {
            "prompt": round(ts["prompt"] / n) if n else 0,
            "completion": round(ts["completion"] / n) if n else 0,
            "total": round(ts["total"] / n) if n else 0,
        }
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
        "provider": cfg["provider_name"],
        "model": cfg["model_id"],
        "thinking": cfg["thinking"],
        "problems": problems,
    }


# ---- Problem 操作 ----

async def sync_problems_from_disk():
    """从文件系统全量同步题目到数据库（id = 目录名，文件是权威来源）"""
    from .config import PROBLEMS_DIR
    if not PROBLEMS_DIR.exists():
        return
    _logger = logging.getLogger(__name__)
    db = await get_db()
    synced = 0
    for d in sorted(PROBLEMS_DIR.iterdir()):
        json_path = d / "problem.json"
        if not d.is_dir() or not json_path.exists():
            continue
        try:
            meta = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning(f"sync_problems_from_disk: skipping {d.name}: {e}")
            continue
        problem_id = d.name
        scoring = meta.get("scoring", {})
        if scoring:
            total_weight = sum(v for v in scoring.values() if isinstance(v, (int, float)))
            if total_weight != 100:
                _logger.warning(f"Problem {problem_id}: scoring weights sum to {total_weight}, expected 100")
        await db.execute(
            """INSERT INTO problems (id, title, difficulty, language, tags, compile_flags,
               timeout_seconds, concurrent, perf_baseline_ms, scoring)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, difficulty=excluded.difficulty,
                 language=excluded.language, tags=excluded.tags,
                 compile_flags=excluded.compile_flags, timeout_seconds=excluded.timeout_seconds,
                 concurrent=excluded.concurrent, perf_baseline_ms=excluded.perf_baseline_ms,
                 scoring=excluded.scoring""",
            (problem_id, meta.get("title", problem_id),
             meta.get("difficulty", "medium"), meta.get("language", "c"),
             json.dumps(meta.get("tags", [])), meta.get("compile_flags", ""),
             meta.get("timeout_seconds", 30), int(meta.get("concurrent", True)),
             meta.get("perf_baseline_ms", 0), json.dumps(scoring))
        )
        synced += 1
    await db.commit()
    _logger.info(f"sync_problems_from_disk: synced {synced} problems")


async def list_problems_db() -> list[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM problems ORDER BY id") as cur:
        rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["scoring"] = json.loads(d.get("scoring", "{}"))
        d["concurrent"] = bool(d.get("concurrent", 1))
        result.append(d)
    return result


async def get_problem(problem_id: str) -> Optional[dict]:
    db = await get_db()
    async with db.execute("SELECT * FROM problems WHERE id=?", (problem_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["tags"] = json.loads(d.get("tags", "[]"))
    d["scoring"] = json.loads(d.get("scoring", "{}"))
    d["concurrent"] = bool(d.get("concurrent", 1))
    return d
