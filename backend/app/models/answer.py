"""答卷(AnswerObject)与证据(Evidence)."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin
from app.db import Base


class Answer(TimestampMixin, Base):
    """统一答案解析输出: AnswerObject.

    modality: text/audio/video; content: 规范化文本(主观题/口语转写/填空等);
    segments: 分段(词级时间戳或 OCR 块坐标, 见 parsers);
    quality: {quality_score, flags, notes} —— 质量门控结果.
    """
    __tablename__ = "answers"

    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    student_token: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    modality: Mapped[str] = mapped_column(String(16))     # text/audio/video
    # 文本内容(规范化后); 音频题存转写文本; 视频题为占位描述
    content: Mapped[str] = mapped_column(Text, default="")
    # 原始提交(选择题字母/答案串等)保留便于展示
    raw_response: Mapped[str] = mapped_column(Text, default="")
    content_uri: Mapped[str] = mapped_column(String(512), default="")  # 上传文件/录音路径
    segments: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    graded: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")  # 异常样例的可解释失败原因


class Evidence(TimestampMixin, Base):
    """评分证据对象: 每个得分点的依据.

    source_type: text / audio / video; label 见 verdict 常量;
    ref_start/ref_end: 文本为字符区间[start,end), 音频/视频为毫秒时间戳;
    text_snippet: 证据原文片段.
    """
    __tablename__ = "evidence"

    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"), index=True)
    score_id: Mapped[int | None] = mapped_column(ForeignKey("scores.id"), nullable=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    point_id: Mapped[str] = mapped_column(String(32), default="")   # 得分点编号(P1/P2...)
    source_type: Mapped[str] = mapped_column(String(16), default="text")
    ref_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(24))                  # verdict 或 "evidence"/"penalty"
    kind: Mapped[str] = mapped_column(String(32), default="")
    text_snippet: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_by: Mapped[str] = mapped_column(String(64), default="engine")  # engine/llm/teacher
