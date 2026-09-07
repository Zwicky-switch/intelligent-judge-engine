"""课程 / 章节 / 知识节点 / 能力域与二级能力维度(图谱结构)."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin
from app.db import Base


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Chapter(TimestampMixin, Base):
    __tablename__ = "chapters"

    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(128))


class KnowledgeNode(TimestampMixin, Base):
    """知识节点(如 K-受力分析). code 即方案中的 node 标识."""
    __tablename__ = "knowledge_nodes"

    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    # 先修节点 code 列表
    prereq_codes: Mapped[list] = mapped_column(JSON, default=list)


class SkillDomain(TimestampMixin, Base):
    """6 个一级能力域(知识理解/问题解决/实践操作/表达沟通/批判与创新/学习迁移)."""
    __tablename__ = "skill_domains"

    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class SkillDimension(TimestampMixin, Base):
    """60 个可配置二级能力维度(每域 10 个), 可关闭."""
    __tablename__ = "skill_dimensions"

    domain_code: Mapped[str] = mapped_column(ForeignKey("skill_domains.code"), index=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    definition: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class CourseDimensionToggle(TimestampMixin, Base):
    """课程级能力维度开关(absent 行 = 启用; 仅写入 enabled=False 的"停用"行).

    停用某维度 -> 该维度不进能力画像聚合, 诊断报告中 enabled=False 置灰。
    """
    __tablename__ = "course_dimension_toggles"
    __table_args__ = {"sqlite_autoincrement": True}

    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    dimension_code: Mapped[str] = mapped_column(String(48), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
