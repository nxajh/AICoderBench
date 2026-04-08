"""
题目加载器
从 problems/ 目录加载题目定义
"""
import json
import os
import shutil
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from ..config import PROBLEMS_DIR


class ScoringConfig(BaseModel):
    compile: int = 10
    tests: int = 25
    safety: int = 25
    quality: int = 15
    resource: int = 15
    performance: int = 10


class Problem(BaseModel):
    id: str
    title: str
    difficulty: str  # easy / medium / hard
    language: str = "c"
    tags: list[str] = []
    description: str = ""
    interface_h: str = ""       # solution.h 内容
    compile_flags: str = ""     # 额外编译参数，如 -lpthread -lm
    timeout_seconds: int = 30
    has_benchmark: bool = False
    scoring: ScoringConfig = ScoringConfig()
    concurrent: bool = True
    perf_baseline_ms: int = 100


def _find_problem_dir(problem_id: str) -> Path:
    """根据 id 或目录名查找题目目录"""
    # 先尝试直接匹配目录名
    d = PROBLEMS_DIR / problem_id
    if d.exists() and (d / "problem.json").exists():
        return d
    # 遍历查找 id 匹配
    for d in PROBLEMS_DIR.iterdir():
        if d.is_dir() and (d / "problem.json").exists():
            meta = json.loads((d / "problem.json").read_text())
            if meta.get("id") == problem_id:
                return d
    raise FileNotFoundError(f"Problem not found: {problem_id}")


def load_problem(problem_id: str) -> Problem:
    """加载单个题目"""
    problem_dir = _find_problem_dir(problem_id)

    meta_path = problem_dir / "problem.json"
    with open(meta_path) as f:
        meta = json.load(f)

    # 加载接口头文件
    interface_path = problem_dir / "solution.h"
    interface_h = ""
    if interface_path.exists():
        interface_h = interface_path.read_text()

    # 加载题目描述
    desc_path = problem_dir / "problem.md"
    description = ""
    if desc_path.exists():
        description = desc_path.read_text()

    return Problem(
        id=meta["id"],
        title=meta["title"],
        difficulty=meta.get("difficulty", "medium"),
        language=meta.get("language", "c"),
        tags=meta.get("tags", []),
        description=description,
        interface_h=interface_h,
        compile_flags=meta.get("compile_flags", ""),
        timeout_seconds=meta.get("timeout_seconds", 30),
        has_benchmark=meta.get("has_benchmark", False),
        scoring=ScoringConfig(**meta.get("scoring", {})),
    )


def list_problems() -> list[Problem]:
    """列出所有题目"""
    problems = []
    if not PROBLEMS_DIR.exists():
        return problems
    for d in sorted(PROBLEMS_DIR.iterdir()):
        if d.is_dir() and (d / "problem.json").exists():
            problems.append(load_problem(d.name))
    return problems


def create_problem(
    id: str,
    title: str,
    difficulty: str = "medium",
    tags: list[str] | None = None,
    language: str = "c",
    compile_flags: str = "",
    timeout_seconds: int = 30,
    scoring: dict | None = None,
    description: str = "",
    interface_h: str = "",
) -> Problem:
    """创建新题目"""
    problem_dir = PROBLEMS_DIR / id
    if problem_dir.exists():
        raise FileExistsError(f"Problem directory already exists: {id}")

    problem_dir.mkdir(parents=True, exist_ok=True)

    scoring_cfg = ScoringConfig(**(scoring or {}))

    meta = {
        "id": id,
        "title": title,
        "difficulty": difficulty,
        "language": language,
        "tags": tags or [],
        "compile_flags": compile_flags,
        "timeout_seconds": timeout_seconds,
        "has_benchmark": False,
        "scoring": scoring_cfg.model_dump(),
    }

    (problem_dir / "problem.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    (problem_dir / "problem.md").write_text(description)
    (problem_dir / "solution.h").write_text(interface_h)

    # 创建 test_framework.h 符号链接
    symlink_path = problem_dir / "test_framework.h"
    if not symlink_path.exists():
        os.symlink("../test_framework.h", symlink_path)

    return load_problem(id)


def update_problem(
    problem_id: str,
    title: str | None = None,
    difficulty: str | None = None,
    tags: list[str] | None = None,
    language: str | None = None,
    compile_flags: str | None = None,
    timeout_seconds: int | None = None,
    scoring: dict | None = None,
    description: str | None = None,
    interface_h: str | None = None,
) -> Problem:
    """更新已有题目"""
    problem_dir = _find_problem_dir(problem_id)

    meta_path = problem_dir / "problem.json"
    meta = json.loads(meta_path.read_text())

    if title is not None:
        meta["title"] = title
    if difficulty is not None:
        meta["difficulty"] = difficulty
    if tags is not None:
        meta["tags"] = tags
    if language is not None:
        meta["language"] = language
    if compile_flags is not None:
        meta["compile_flags"] = compile_flags
    if timeout_seconds is not None:
        meta["timeout_seconds"] = timeout_seconds
    if scoring is not None:
        existing = meta.get("scoring", {})
        existing.update(scoring)
        meta["scoring"] = existing

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    if description is not None:
        (problem_dir / "problem.md").write_text(description)
    if interface_h is not None:
        (problem_dir / "solution.h").write_text(interface_h)

    return load_problem(problem_id)


def update_test_file(problem_id: str, test_c: str) -> None:
    """更新测试文件"""
    problem_dir = _find_problem_dir(problem_id)
    (problem_dir / "test.c").write_text(test_c)


def delete_problem(problem_id: str) -> None:
    """删除题目"""
    problem_dir = _find_problem_dir(problem_id)
    shutil.rmtree(problem_dir)
