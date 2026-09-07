"""成绩查询: 列表 / 详情(含证据与复核轨迹) / 学生逐题概览."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.constants import ROLE_STUDENT
from app.core.deps import CurrentUser, get_current_user
from app.db import get_db
from app.models import Answer, Evidence, Item, ReviewRecord, Score, User

from app.api.serializers import (
    answer_dict, evidence_dict, item_dict, score_dict, user_dict,
)

router = APIRouter(prefix="/scores", tags=["成绩"])


def _load_evidence(db: Session, score_id: int) -> list:
    return (db.query(Evidence).filter(Evidence.score_id == score_id)
            .order_by(Evidence.id).all())


def _student_name(db: Session, token: str) -> str:
    u = db.query(User).filter(User.student_token == token).first()
    return u.display_name if u else token


@router.get("")
def list_scores(
    student_token: str | None = None,
    item_id: int | None = None,
    status: str | None = None,
    cur: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Score)
    # 学生只能看自己
    if cur.role == ROLE_STUDENT:
        q = q.filter(Score.student_token == cur.student_token)
    elif student_token:
        q = q.filter(Score.student_token == student_token)
    if item_id is not None:
        q = q.filter(Score.item_id == item_id)
    if status:
        q = q.filter(Score.status == status)
    rows = q.order_by(Score.created_at.desc()).limit(300).all()
    items = {i.id: i for i in db.query(Item).all()}
    names = {t: _student_name(db, t) for t in {r.student_token for r in rows}}
    out = []
    for r in rows:
        d = score_dict(r, item=items.get(r.item_id), include_evidence=_load_evidence(db, r.id))
        d["student_name"] = names.get(r.student_token)
        out.append(d)
    return {"items": out, "total": len(out)}


@router.get("/overview/{student_token}")
def student_overview(student_token: str,
                     cur: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if cur.role == ROLE_STUDENT and student_token != cur.student_token:
        raise HTTPException(403, "无权查看他人成绩")
    if cur.role != ROLE_STUDENT:
        user = db.query(User).filter(User.student_token == student_token).first()
        if user is None:
            raise HTTPException(404, "学生不存在")
    name = _student_name(db, student_token)
    # 每道题仅保留该生最后一次作答
    items = (db.query(Item).filter(Item.enabled.is_(True)).order_by(Item.code).all())
    attempts = []
    for it in items:
        score = (db.query(Score)
                 .join(Answer, Answer.id == Score.answer_id)
                 .filter(Answer.student_token == student_token, Score.item_id == it.id)
                 .order_by(Score.id.desc()).first())
        if score is None:
            continue
        answer = db.get(Answer, score.answer_id)
        attempts.append({
            "item": item_dict(it),
            "answer": answer_dict(answer) if answer else None,
            "score": score_dict(score, include_evidence=_load_evidence(db, score.id)),
        })
    return {"student_token": student_token, "student_name": name, "attempts": attempts}


@router.get("/{score_id}")
def get_score(score_id: int, cur: CurrentUser = Depends(get_current_user),
              db: Session = Depends(get_db)):
    sc = db.get(Score, score_id)
    if sc is None:
        raise HTTPException(404, "成绩不存在")
    if cur.role == ROLE_STUDENT and sc.student_token != cur.student_token:
        raise HTTPException(403, "无权查看他人成绩")
    item = db.get(Item, sc.item_id)
    answer = db.get(Answer, sc.answer_id)
    records = (db.query(ReviewRecord).filter(ReviewRecord.score_id == score_id)
               .order_by(ReviewRecord.id).all())
    d = score_dict(sc, answer=answer, item=item, include_answer=True,
                   include_evidence=_load_evidence(db, score_id))
    d["review_records"] = [
        {"id": r.id, "action": r.action, "old_score": r.old_score,
         "new_score": r.new_score, "comment": r.comment, "reviewed_by": r.reviewed_by,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in records]
    d["student_name"] = _student_name(db, sc.student_token)
    return d
