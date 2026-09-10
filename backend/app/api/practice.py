"""学生自主练习: 浏览已发布/启用的可作答题目列表并自行提交.

覆盖题型: 客观题(选择/填空/数值)+ 文本主观题 + 口语题(文本转写模拟)+ 实操视频题(上传视频,
服务端转写音轨后按步骤量规判分).
**绝不泄露答案**: 只下发 UI 渲染所需的最小配置; 不返回 correct/参考答案/量规/术语库.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.constants import (
    ITEM_MODALITY, ITEM_TYPE_LABELS, MODALITY_TEXT, OBJECTIVE_TYPES,
    T_FORMULA, T_MULTIPLE_CHOICE, T_SINGLE_CHOICE, T_SPOKEN, T_SUBJECTIVE_TEXT,
    T_VIDEO,
)
from app.core.deps import CurrentUser, get_current_user
from app.db import get_db
from app.models import Answer, Chapter, Course, Item, Score

router = APIRouter(prefix="/practice", tags=["自主练习"])

# 学生可在练习区作答的题型(公式题输入字母表达式)
PRACTICE_TYPES = OBJECTIVE_TYPES | {T_SUBJECTIVE_TEXT, T_SPOKEN, T_VIDEO, T_FORMULA}

# 仅向学生开放可见的题目配置字段(选择题才给选项; 绝不返回 correct/答案/量规/术语库)
_OPTION_CFG_KEYS = {
    T_SINGLE_CHOICE: ("options",),
    T_MULTIPLE_CHOICE: ("options",),
}


@router.get("/items")
def practice_items(course_id: int | None = Query(default=None),
                   cur: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    q = db.query(Item).filter(Item.published.is_(True), Item.enabled.is_(True),
                              Item.type.in_(PRACTICE_TYPES))
    if course_id is not None:
        q = q.filter(Item.course_id == course_id)
    rows = q.order_by(Item.code).all()
    courses = {c.id: c for c in db.query(Course).all()}
    chapters = {ch.id: ch for ch in db.query(Chapter).all()}
    answered = {
        a.item_id for a in db.query(Answer).filter(Answer.student_token == cur.student_token).all()
    } if cur.student_token else set()
    # 学生最近一次作答该题时固化的题目版本(用于前端: 重新发布出新版本后题目重新出现)
    answered_version: dict[int, int] = {}
    if cur.student_token:
        from sqlalchemy import func
        ver_rows = (db.query(Score.item_id, func.max(Score.item_version))
                    .filter(Score.student_token == cur.student_token,
                            Score.item_id.in_(answered or [-1]))
                    .group_by(Score.item_id).all())
        answered_version = {iid: ver for iid, ver in ver_rows}
    out = []
    for it in rows:
        cfg = it.answer_config or {}
        public_cfg: dict = {}
        for k in _OPTION_CFG_KEYS.get(it.type, ()):
            if k in cfg:
                public_cfg[k] = cfg[k]
        out.append({
            "id": it.id, "code": it.code, "type": it.type,
            "type_label": ITEM_TYPE_LABELS.get(it.type, it.type),
            "title": it.title, "max_score": it.max_score,
            "course_name": courses.get(it.course_id).name if it.course_id in courses else "",
            "chapter_name": chapters.get(it.chapter_id).name if it.chapter_id in chapters else "",
            "knowledge_nodes": it.knowledge_nodes or [],
            "modality": ITEM_MODALITY.get(it.type, MODALITY_TEXT),
            "public_config": public_cfg,
            "answered": it.id in answered,
            "answered_version": answered_version.get(it.id),
            "current_version": it.current_version,
            "published_at": it.published_at.isoformat() if it.published_at else None,
            "submit_deadline": it.submit_deadline.isoformat() if it.submit_deadline else None,
        })
    return {"items": out, "total": len(out)}
