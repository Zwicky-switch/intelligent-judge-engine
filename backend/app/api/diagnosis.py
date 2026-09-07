"""能力诊断与学习报告: 实时计算 + 落库(Diagnosis)供报告页渲染."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.constants import (
    ABILITY_DOMAINS, MODEL_VERSION, ROLE_STUDENT,
)
from app.core.deps import CurrentUser, get_current_user
from app.db import get_db
from app.diagnostics.mastery import (
    compute_mastery, compute_overall_confidence,
)
from app.diagnostics.recommender import build_recommendations
from app.models import Course, Diagnosis, User

from app.api.serializers import DOMAIN_LABELS

router = APIRouter(prefix="/diagnosis", tags=["能力诊断"])


def _compute_report(db: Session, student_token: str, course_id: int) -> dict:
    mastery = compute_mastery(db, student_token, course_id)
    recs = build_recommendations(db, mastery["node_mastery"])
    confidence = compute_overall_confidence(mastery)

    ability = {}
    for code, _name in ABILITY_DOMAINS:
        v = mastery.get("ability", {}).get(code)
        ability[code] = {"score": v["score"] if v else None,
                         "label": _name,
                         "observed": v["observed"] if v else 0}
    # 持久化诊断画像
    diag = (db.query(Diagnosis)
            .filter(Diagnosis.student_token == student_token,
                    Diagnosis.course_id == course_id).first())
    if diag is None:
        diag = Diagnosis(student_token=student_token, course_id=course_id)
        db.add(diag)
    diag.ability_vector = mastery.get("ability", {})
    diag.node_mastery = mastery.get("node_mastery", {})
    diag.ability_theta = mastery.get("theta")
    diag.recommendations = recs
    diag.confidence = confidence
    diag.observed_items = mastery.get("observed", 0)
    diag.model_version = MODEL_VERSION
    diag.computed_at = datetime.now(timezone.utc)
    diag.detail = mastery.get("detail", "")
    db.commit()

    # 知识节点全量目录(含未观测节点, 供热力图/节点表展示; 未观测 mastery=None 置灰)
    from app.models import Chapter, KnowledgeNode
    ch_rows = db.query(Chapter).filter(Chapter.course_id == course_id).all()
    ch_name = {c.id: c.name for c in ch_rows}
    nodes = (db.query(KnowledgeNode)
             .filter(KnowledgeNode.chapter_id.in_([c.id for c in ch_rows]))
             .all()) if ch_rows else []
    node_catalog = dict(mastery.get("node_mastery", {}))
    for n in nodes:
        entry = dict(node_catalog.get(n.code) or
                     {"mastery": None, "raw": None, "confidence": None, "observed": 0})
        entry.update({"name": n.name, "code": n.code,
                      "chapter_id": n.chapter_id,
                      "chapter_name": ch_name.get(n.chapter_id, "")})
        node_catalog[n.code] = entry

    course = db.get(Course, course_id)
    u = db.query(User).filter(User.student_token == student_token).first()
    return {
        "student_token": student_token,
        "student_name": u.display_name if u else student_token,
        "course_id": course_id,
        "course_name": course.name if course else "",
        "ability": ability,
        "dimensions": mastery.get("dimension", {}),
        "node_mastery": node_catalog,
        "profile_match": mastery.get("profile_match"),
        "theta": mastery.get("theta"),
        "recommendations": recs,
        "observed": mastery.get("observed", 0),
        "confidence": confidence,
        "model_version": MODEL_VERSION,
        "computed_at": diag.computed_at.isoformat() if diag.computed_at else None,
        "algorithm_detail": mastery.get("detail", ""),
        "domain_labels": DOMAIN_LABELS,
    }


def _resolve_course(db: Session, cur: CurrentUser, course_id: int | None) -> int:
    if course_id:
        return course_id
    c = db.query(Course).first()
    if c is None:
        raise HTTPException(404, "尚无课程数据")
    return c.id


@router.get("/{student_token}")
def get_diagnosis(student_token: str, course_id: int | None = None,
                  cur: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if cur.role == ROLE_STUDENT:
        if student_token != cur.student_token:
            raise HTTPException(403, "学生只能查看本人报告")
    else:
        if db.query(User).filter(User.student_token == student_token).first() is None:
            raise HTTPException(404, "学生不存在")
    cid = _resolve_course(db, cur, course_id)
    return _compute_report(db, student_token, cid)


# 快捷入口: 学生个人报告(无需在 URL 写 token)
@router.get("/mine/current")
def my_diagnosis(course_id: int | None = None,
                 cur: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    if cur.role != ROLE_STUDENT or not cur.student_token:
        raise HTTPException(403, "仅学生账号可访问个人报告")
    cid = _resolve_course(db, cur, course_id)
    return _compute_report(db, cur.student_token, cid)
