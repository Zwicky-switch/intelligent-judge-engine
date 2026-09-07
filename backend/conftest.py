"""pytest 全局配置: 测试用内存库 + 离线评阅模型."""
from __future__ import annotations

import os

# 必须在任何 app 模块 import 之前设置
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GRADE_LLM_PROVIDER", "mock")
os.environ.setdefault("GRADE_LLM_API_KEY", "")
os.environ.setdefault("AUTO_SEED_ON_START", "false")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_db():
    from app.db import Base, engine
    from app import models  # noqa: F401  (先注册表, 否则 create_all 为空操作)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client():
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
