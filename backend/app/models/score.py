"""评分(Score)、复核记录(ReviewRecord)、审计日志(AuditLog, 不可删除)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin
from app.db import Base


class Score(TimestampMixin, Base):
    """一道答卷的一次评阅结果.

    status: pending/auto_passed/needs_review/reviewed
    review_level: none/sample/forced (三档复核)
    total_score: 模型/规则计算分; final_score: 终审分(复核或自动放行后落定)
    """
    __tablename__ = "scores"

    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    student_token: Mapped[str] = mapped_column(String(64), index=True)
    item_version: Mapped[int] = mapped_column(Integer, default=1)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    max_score: Mapped[float] = mapped_column(Float, default=10.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 得分点明细 [{point_id, description, status, earned, reason, max}]
    point_scores: Mapped[list] = mapped_column(JSON, default=list)
    penalties: Mapped[list] = mapped_column(JSON, default=list)
    # 总分/能力占比, 0-1; 越低越要人工
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    review_level: Mapped[str] = mapped_column(String(16), default="none")
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    comment: Mapped[str] = mapped_column(Text, default="")       # 建议评语(可被教师改)
    reasoning: Mapped[str] = mapped_column(Text, default="")     # 引擎解释/可读理由
    error: Mapped[str] = mapped_column(Text, default="")         # 异常可解释原因
    assessment_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 引擎元数据(JSON): elapsed_ms 评阅耗时; 口语 extra.layers(四层明细); quality 等
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ReviewRecord(TimestampMixin, Base):
    """教师复核/仲裁操作记录(每次 action 一行)."""
    __tablename__ = "review_records"

    score_id: Mapped[int] = mapped_column(ForeignKey("scores.id"), index=True)
    action: Mapped[str] = mapped_column(String(24))   # accept/adjust/arbitrate/return_model
    old_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditLog(TimestampMixin, Base):
    """不可删除的审计记录(方案 §4.7)."""
    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(64), default="")        # username
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
