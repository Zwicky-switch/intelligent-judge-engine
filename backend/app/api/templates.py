"""量规模板: 一套可复用的得分点结构(命师建库, 命题编辑时下拉套用)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.constants import ROLE_ADMIN, ROLE_PROP_TEACHER
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.models import RubricTemplate

router = APIRouter(prefix="/rubric-templates", tags=["量规模板"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER)


def template_dict(t: RubricTemplate) -> dict:
    return {
        "id": t.id, "name": t.name, "subject": t.subject,
        "course_id": t.course_id, "description": t.description,
        "rubric": t.rubric or [], "enabled": bool(t.enabled),
        "point_count": len(t.rubric or []),
        "total_score": round(sum(float(p.get("score") or 0) for p in (t.rubric or [])), 2),
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class TemplateBody(BaseModel):
    name: str
    subject: str = ""
    course_id: int | None = None
    description: str = ""
    rubric: list = Field(default_factory=list)   # 与 Item.rubric 同构的得分点
    enabled: bool = True


@router.get("")
def list_templates(course_id: int | None = None,
                   subject: str | None = None,
                   cur: CurrentUser = Depends(require_roles(*STAFF)),
                   db: Session = Depends(get_db)):
    q = db.query(RubricTemplate)
    if course_id is not None:
        q = q.filter((RubricTemplate.course_id == course_id)
                     | (RubricTemplate.course_id.is_(None)))
    if subject:
        q = q.filter((RubricTemplate.subject == subject)
                     | (RubricTemplate.subject == ""))
    rows = q.order_by(RubricTemplate.name).all()
    return {"items": [template_dict(t) for t in rows], "total": len(rows)}


@router.post("")
def create_template(body: TemplateBody,
                    cur: CurrentUser = Depends(require_roles(*STAFF)),
                    db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(422, "模板名称不能为空")
    t = RubricTemplate(name=name, subject=body.subject, course_id=body.course_id,
                       description=body.description, rubric=body.rubric or [],
                       enabled=body.enabled, created_by=cur.id)
    db.add(t)
    db.commit()
    return template_dict(t)


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateBody,
                    cur: CurrentUser = Depends(require_roles(*STAFF)),
                    db: Session = Depends(get_db)):
    t = db.get(RubricTemplate, template_id)
    if t is None:
        raise HTTPException(404, "模板不存在")
    t.name = (body.name or "").strip() or t.name
    t.subject = body.subject
    t.course_id = body.course_id
    t.description = body.description
    t.rubric = body.rubric or []
    t.enabled = body.enabled
    db.commit()
    return template_dict(t)


@router.delete("/{template_id}")
def delete_template(template_id: int,
                    cur: CurrentUser = Depends(require_roles(*STAFF)),
                    db: Session = Depends(get_db)):
    t = db.get(RubricTemplate, template_id)
    if t is None:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return {"ok": True}
