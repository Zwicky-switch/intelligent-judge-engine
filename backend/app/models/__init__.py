"""ORM 模型汇总(import 即注册到 Base.metadata)."""
from app.models.base import TimestampMixin
from app.models.user import User
from app.models.course import (
    Course, Chapter, KnowledgeNode, SkillDomain, SkillDimension,
    CourseDimensionToggle,
)
from app.models.item import Item, ItemVersion, PublishApproval, RubricTemplate
from app.models.answer import Answer, Evidence
from app.models.score import Score, ReviewRecord, AuditLog
from app.models.diagnosis import Diagnosis, AssessmentJob

__all__ = [
    "TimestampMixin",
    "User", "Course", "Chapter", "KnowledgeNode", "SkillDomain", "SkillDimension",
    "Item", "ItemVersion", "RubricTemplate", "PublishApproval",
    "Answer", "Evidence",
    "Score", "ReviewRecord", "AuditLog",
    "Diagnosis", "AssessmentJob",
]
