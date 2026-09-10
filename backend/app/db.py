"""数据库: SQLAlchemy 2 Engine / Session / Base.

默认 SQLite(文件库 data/app.db), 开箱即用零额外依赖运行;
通过 DAO 层隔离, 后续可无缝切换 PostgreSQL 等。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


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
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


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
