"""题目 / 评分量规 / 版本化 / Q 矩阵(题目-知识节点-能力维度 映射)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, utcnow
from app.db import Base


class Item(TimestampMixin, Base):
    __tablename__ = "items"

    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # PHY-2026-001
    type: Mapped[str] = mapped_column(String(32), index=True)               # constants.ALL_ITEM_TYPES
    title: Mapped[str] = mapped_column(Text)                                # 题干 / 场景描述
    # 题型专属配置(标准答案/选项/容差/术语库等)
    answer_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 评分量规: 主观题/口语题/视频题 -> 得分点列表; 其余题型可为空
    rubric: Mapped[list] = mapped_column(JSON, default=list)
    # 参考答案(主观题), 供判点与给 LLM 提示
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    cognitive_level: Mapped[str] = mapped_column(String(32), default="apply")  # Bloom: remember/understand/apply/analyze/evaluate/create
    # Q 矩阵: 考查知识节点 code 列表
    knowledge_nodes: Mapped[list] = mapped_column(JSON, default=list)
    # 每知识节点对应的能力维度 code 与权重: {node_code: {dimension: code, weight: w}}
    q_matrix: Mapped[dict] = mapped_column(JSON, default=dict)
    max_score: Mapped[float] = mapped_column(Float, default=10.0)
    # 评分策略(可被前端查看): 容差/复核阈值/自动放行/惩罚项
    scoring_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    # 难度/区分度(供诊断 IRT 使用)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    discrimination: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    # 发布时间(最近一次真正发布/修订发布的时刻, 发布动作自动写入)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 提交截止时间(教师配置, 空=不限时; 学生端超时禁止提交且后端校验)
    submit_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ItemVersion(TimestampMixin, Base):
    """发布时固化的量规/答案快照, 历史成绩不回写."""
    __tablename__ = "item_versions"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    rubric: Mapped[list] = mapped_column(JSON, default=list)
    answer_config: Mapped[dict] = mapped_column(JSON, default=dict)
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    knowledge_nodes: Mapped[list] = mapped_column(JSON, default=list)
    q_matrix: Mapped[dict] = mapped_column(JSON, default=dict)
    max_score: Mapped[float] = mapped_column(Float, default=10.0)
    scoring_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RubricTemplate(TimestampMixin, Base):
    """量规模板: 命(教)师可复用的一套得分点结构(入库供"套用模板"下拉).

    course_id 为空表示全校通用模板; rubric 为与 Item.rubric 同构的得分点列表。
    """
    __tablename__ = "rubric_templates"

    name: Mapped[str] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(64), default="")   # 适用学科(如 物理/通用)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PublishApproval(TimestampMixin, Base):
    """发布双人复核记录: 一道题需 >=2 个不同账号复核才真正 published(默认单账号兼容)."""
    __tablename__ = "publish_approvals"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(Integer, index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
