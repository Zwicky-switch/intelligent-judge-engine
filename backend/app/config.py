"""运行时配置: 从环境变量 / .env 读取, 提供模块级配置对象."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录 = backend/ 的上一级; .env 可放 repo 根或 backend/ 下
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
REPO_ROOT = BACKEND_DIR.parent                                # .../intelligent-judge-engine

for _dot in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
    if _dot.exists():
        load_dotenv(_dot, override=False)
        break


def _bool(v, default=False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """集中配置. 生产部署时用环境变量覆盖即可, 无需改代码."""

    # ---------- 数据库 ----------
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}",
    )

    # ---------- 存储 ----------
    UPLOAD_DIR: Path = Path(
        os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "data" / "uploads"))
    )

    # ---------- 认证 ----------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "insight-dev-secret-change-me")
    TOKEN_TTL_HOURS: int = int(os.getenv("TOKEN_TTL_HOURS", "24"))

    # ---------- 评阅模型(国产大模型可替换) ----------
    # provider: deepseek / qwen / zhipu / builtin(内置本地引擎, 无需 Key; 兼容历史值 mock)
    GRADE_LLM_PROVIDER: str = os.getenv("GRADE_LLM_PROVIDER", "builtin")
    GRADE_LLM_API_KEY: str = os.getenv("GRADE_LLM_API_KEY", "")
    GRADE_LLM_BASE_URL: str = os.getenv("GRADE_LLM_BASE_URL", "")
    GRADE_LLM_MODEL: str = os.getenv("GRADE_LLM_MODEL", "")

    # ---------- 评阅默认阈值(单题可在 scoring_policy 覆盖) ----------
    REVIEW_THRESHOLD: float = float(os.getenv("REVIEW_THRESHOLD", "0.78"))  # 低信度阈值
    AUTO_RELEASE_OBJECTIVE: bool = _bool(os.getenv("AUTO_RELEASE_OBJECTIVE", "true"))

    # ---------- 启动自动初始化 ----------
    AUTO_SEED_ON_START: bool = _bool(os.getenv("AUTO_SEED_ON_START", "true"))

    def ensure_dirs(self) -> None:
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)
        if self.DATABASE_URL.startswith("sqlite"):
            db_path = self.DATABASE_URL.replace("sqlite:///", "", 1)
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
