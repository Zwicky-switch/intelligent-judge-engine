"""诊断结果(Diagnosis)与批量评阅任务(AssessmentJob)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin
from app.db import Base


class Diagnosis(TimestampMixin, Base):
    """学生-课程 能力画像(方案 §5.3).

    ability_vector: {domain_code: {score, confidence}}
    node_mastery:   {node_code: {mastery, confidence, observed}}
    recommendations:[{type, node, title, priority, reason}]
    """
    __tablename__ = "diagnoses"

    student_token: Mapped[str] = mapped_column(String(64), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    ability_vector: Mapped[dict] = mapped_column(JSON, default=dict)
    node_mastery: Mapped[dict] = mapped_column(JSON, default=dict)
    ability_theta: Mapped[float | None] = mapped_column(Float, nullable=True)  # IRT 估计(可选)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    observed_items: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")   # 算法口径说明


class AssessmentJob(TimestampMixin, Base):
    """批量评阅任务状态(支持异步轮询)."""
    __tablename__ = "assessment_jobs"

    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
