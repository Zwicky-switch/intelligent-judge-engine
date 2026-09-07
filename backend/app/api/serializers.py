"""API 序列化辅助: 统一把 ORM 对象转成前端可直接渲染的 JSON."""
from __future__ import annotations

from app.constants import (
    ABILITY_DOMAINS, ITEM_TYPE_LABELS, ROLE_LABELS, SPOKEN_LAYER_LABELS,
    VERDICT_LABELS,
)
from app.models import Answer, AuditLog, Item, Score, User

DOMAIN_LABELS = dict(ABILITY_DOMAINS)
# 口语四层 label(extra.layers 用)
LAYER_LABELS = SPOKEN_LAYER_LABELS


def user_dict(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name,
        "role": u.role, "role_label": ROLE_LABELS.get(u.role, u.role),
        "student_token": u.student_token, "course_id": u.course_id,
        "active": bool(u.active),
    }


def item_dict(it: Item) -> dict:
    return {
        "id": it.id, "code": it.code, "type": it.type,
        "type_label": ITEM_TYPE_LABELS.get(it.type, it.type),
        "course_id": it.course_id, "chapter_id": it.chapter_id,
        "title": it.title, "max_score": it.max_score,
        "cognitive_level": it.cognitive_level,
        "knowledge_nodes": it.knowledge_nodes or [],
        "q_matrix": it.q_matrix or {},
        "answer_config": it.answer_config or {},
        "rubric": it.rubric or [],
        "reference_answer": it.reference_answer or "",
        "scoring_policy": it.scoring_policy or {},
        "difficulty": it.difficulty, "discrimination": it.discrimination,
        "enabled": bool(it.enabled), "published": bool(it.published),
        "current_version": it.current_version,
    }


def answer_dict(a: Answer) -> dict:
    return {
        "id": a.id, "trace_id": a.trace_id, "student_token": a.student_token,
        "item_id": a.item_id, "modality": a.modality,
        "content": a.content, "raw_response": a.raw_response,
        "content_uri": a.content_uri, "segments": a.segments or [],
        "quality": a.quality or {}, "graded": bool(a.graded),
        "error": a.error, "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def evidence_dict(ev) -> dict:
    return {
        "id": ev.id, "score_id": ev.score_id, "point_id": ev.point_id,
        "source_type": ev.source_type, "ref_start": ev.ref_start, "ref_end": ev.ref_end,
        "label": ev.label, "label_text": VERDICT_LABELS.get(ev.label, ev.label),
        "kind": ev.kind, "text_snippet": ev.text_snippet,
        "confidence": ev.confidence, "created_by": ev.created_by,
    }


def score_dict(sc: Score, answer: Answer | None = None,
               item: Item | None = None, include_answer=False,
               include_evidence: list | None = None) -> dict:
    d = {
        "id": sc.id, "answer_id": sc.answer_id, "item_id": sc.item_id,
        "student_token": sc.student_token,
        "item_version": sc.item_version, "model_version": sc.model_version,
        "max_score": sc.max_score, "total_score": sc.total_score,
        "final_score": sc.final_score,
        "point_scores": sc.point_scores or [],
        "penalties": sc.penalties or [],
        "confidence": sc.confidence, "status": sc.status,
        "review_level": sc.review_level, "review_round": sc.review_round,
        "comment": sc.comment, "reasoning": sc.reasoning, "error": sc.error,
        "assessment_job_id": sc.assessment_job_id,
        "reviewed_at": sc.reviewed_at.isoformat() if sc.reviewed_at else None,
        "reviewed_by": sc.reviewed_by,
        "extra": sc.extra or {},
        "created_at": sc.created_at.isoformat() if sc.created_at else None,
    }
    if include_answer and answer:
        d["answer"] = answer_dict(answer)
    if item:
        d["item"] = item_dict(item)
    if include_evidence is not None:
        d["evidence"] = [evidence_dict(ev) for ev in include_evidence]
    return d


def audit_dict(a: AuditLog) -> dict:
    return {
        "id": a.id, "actor": a.actor, "actor_id": a.actor_id, "action": a.action,
        "target_type": a.target_type, "target_id": a.target_id, "detail": a.detail or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
