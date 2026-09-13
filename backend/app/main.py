"""FastAPI 应用工厂: 挂载 /v1 各路由 + CORS + 启动自动建表/注入初始化示例数据."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.constants import MODEL_VERSION
from app.db import SessionLocal, init_db
from app.llm.base import normalize_provider

logger = logging.getLogger("app")



def _auto_init() -> None:
    """建表 + (可选)首次启动注入初始化示例数据."""
    import app.models  # noqa: F401  (注册所有 ORM 表)
    init_db()
    if settings.AUTO_SEED_ON_START:
        db = SessionLocal()
        try:
            from app.seeds.demo import ensure_seeded
            if ensure_seeded(db):
                logger.info("已注入初始化示例数据(大学物理课程/学生/答卷并完成评阅)。")
            else:
                logger.info("数据库已有数据, 跳过初始化。")
        finally:
            db.close()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _auto_init()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="智评·Insight — 多题型智能评阅与能力诊断引擎",
        version=MODEL_VERSION,
        description="证据优先的智能评阅 + 能力诊断闭环 API(客观题确定性判分 / 主观·口语大模型协同 / 教师复核仲裁 / IRT 与 Q矩阵诊断)。",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],            # 默认放开便于本地部署; 正式部署收敛为前端域名
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_timing_middleware(request: Request, call_next):
        """端到端请求耗时中间件: 记录含 HTTP/上传/ASR/OCR/持久化的全链路耗时.

        引擎内部 elapsed_ms 仅含判分逻辑; 本中间件补齐端到端口径,
        便于定位真实用户感知延迟的瓶颈(上传/ASR/OCR vs 引擎本身)。
        """
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.2f}"
        # 慢请求(>1s)记录到日志, 便于排查
        if elapsed_ms > 1000:
            logger.info("慢请求 %s %s -> %.0fms", request.method, request.url.path, elapsed_ms)
        return response

    from app.api import (
        answers, assessments, audit, auth, courses, diagnosis, items,
        knowledge, meta, metrics, practice, reviews, scores, templates,
    )
    # 各资源路由统一挂 /v1 前缀
    for r in (auth, courses, knowledge, items, answers, assessments,
              scores, reviews, diagnosis, meta, metrics, audit, practice, templates):
        app.include_router(r.router, prefix="/v1")

    @app.get("/")
    def root():
        return {
            "service": "智评·Insight",
            "version": MODEL_VERSION,
            "status": "ok",
            "llm_provider": normalize_provider(),
            "docs": "/docs",
        }

    return app


app = create_app()
