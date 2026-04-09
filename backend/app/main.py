"""
AICoderBench — AI编码能力评测平台
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router
from .config import RESULTS_DIR, PROBLEMS_DIR, SANDBOX_CONCURRENCY
from . import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)
    await db.init_db()                      # 建表 + 迁移 + 首次同步题目
    await db.sync_problems_from_disk()      # 全量 upsert：确保文件变更被应用
    _log = logging.getLogger(__name__)
    _log.info("Database initialized and problems synced")
    _log.info(f"Sandbox concurrency: {SANDBOX_CONCURRENCY} "
              f"(set SANDBOX_CONCURRENCY=N to override)")
    yield


app = FastAPI(
    title="AICoderBench",
    description="AI编码能力自动评测平台",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许的来源：可通过 CORS_ORIGINS 环境变量配置，默认允许本地开发地址
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_allowed_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000", "http://frontend:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,  # allow_credentials=True 与 allow_origins=["*"] 组合在规范中无效
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(router, prefix="/api")
