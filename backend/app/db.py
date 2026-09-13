"""数据库: SQLAlchemy 2 Engine / Session / Base.

默认 SQLite(文件库 data/app.db), 开箱即用零额外依赖运行;
通过 DAO 层隔离, 后续可无缝切换 PostgreSQL 等。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类."""


def _make_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # SQLite 线程安全: 允许跨线程共享连接(供线程池/后台任务使用)
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            # 内存库使用单连接, 保证测试各 session 看到同一数据
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # 文件库: 启用 WAL 模式提升并发读写性能(写不阻塞读),
            # 并设置合理的连接池大小与回收超时。
            kwargs["pool_size"] = 10
            kwargs["max_overflow"] = 20
            kwargs["pool_recycle"] = 1800
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _enable_sqlite_wal() -> None:
    """对文件型 SQLite 启用 WAL(Write-Ahead Logging) 模式.

    WAL 允许多读单写并发, 显著提升高并发下的读性能; 对单写多读的
    评阅场景(提交写 + 看板/列表读)效果明显。内存库跳过。
    """
    url = settings.DATABASE_URL
    if not url.startswith("sqlite") or ":memory:" in url:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.execute(text("PRAGMA temp_store=MEMORY"))
            conn.execute(text("PRAGMA cache_size=-20000"))  # 20MB 页缓存
        logger.info("SQLite WAL 模式已启用")
    except Exception:  # noqa: BLE001
        logger.warning("SQLite WAL 启用失败, 回退默认模式", exc_info=True)


def _ensure_columns() -> None:
    """幂等补齐 additive 列.

    create_all 只会新建表, 不会给已存在的表加列(SQLite 等).
    每次启动做一次 PRAGMA 检查, 缺列则 ALTER TABLE ADD COLUMN.
    """
    try:
        insp = inspect(engine)
        if "scores" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("scores")}
            if "extra" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE scores ADD COLUMN extra JSON"))
        if "items" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("items")}
            with engine.begin() as conn:
                if "published_at" not in cols:
                    conn.execute(text("ALTER TABLE items ADD COLUMN published_at DATETIME"))
                if "submit_deadline" not in cols:
                    conn.execute(text("ALTER TABLE items ADD COLUMN submit_deadline DATETIME"))
    except Exception:  # noqa: BLE001  (老库兼容失败不阻塞启动)
        pass


def init_db() -> None:
    """建表(幂等). 需要先 import 所有 model 以注册到 Base.metadata."""
    from app import models  # noqa: F401  (注册表)

    _enable_sqlite_wal()
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def drop_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)


@contextmanager
def session_scope() -> Iterator:
    """事务化 session 上下文. 提交或回滚后统一关闭."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI 依赖."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
