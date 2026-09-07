"""知识图谱: 课程 -> 章节 -> 知识节点; 能力域 -> 二级维度; 课程能力维度开关."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constants import ABILITY_DOMAINS, ROLE_ADMIN, ROLE_PROP_TEACHER
from app.core.deps import CurrentUser, get_current_user, require_roles
from app.db import get_db
from app.models import (
    Chapter, Course, CourseDimensionToggle, KnowledgeNode,
    SkillDimension, SkillDomain,
)

router = APIRouter(tags=["知识图谱"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER)


@router.get("/courses/{course_id}/knowledge")
def course_knowledge(course_id: int, cur: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(404, "课程不存在")
    chapters = (db.query(Chapter).filter(Chapter.course_id == course_id)
                .order_by(Chapter.order_index).all())
    nodes = {ch.id: [] for ch in chapters}
    for n in (db.query(KnowledgeNode)
              .filter(KnowledgeNode.chapter_id.in_([ch.id for ch in chapters]))
              .order_by(KnowledgeNode.code).all()):
        nodes.setdefault(n.chapter_id, []).append({
            "id": n.id, "code": n.code, "name": n.name, "description": n.description,
            "prereq_codes": n.prereq_codes or [],
        })
    return {
        "course_id": course_id, "course_name": c.name,
        "chapters": [{"id": ch.id, "order_index": ch.order_index, "name": ch.name,
                      "nodes": nodes.get(ch.id, [])} for ch in chapters],
    }


@router.get("/dimensions")
def list_dimensions(cur: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    domains = db.query(SkillDomain).order_by(SkillDomain.order_index).all()
    dims = db.query(SkillDimension).all()
    by_domain: dict[str, list] = {}
    for d in dims:
        by_domain.setdefault(d.domain_code, []).append({
            "code": d.code, "name": d.name, "enabled": bool(d.enabled),
            "order_index": d.order_index, "weight": d.weight, "definition": d.definition,
        })
    return {"domains": [{
        "code": d.code, "name": d.name, "order_index": d.order_index,
        "dimensions": sorted(by_domain.get(d.code, []), key=lambda x: x["order_index"]),
    } for d in domains]}


# 能力域常量(供前端渲染雷达/看板, 不依赖库)
@router.get("/ability-domains")
def ability_domains(cur: CurrentUser = Depends(get_current_user)):
    return {"domains": [{"code": code, "name": name} for code, name in ABILITY_DOMAINS]}


# ---------------- 课程能力维度开关(M11: 按学科停用, absent=启用) ----------------

def _dimension_rows(db: Session, course_id: int) -> tuple[list[dict], dict]:
    doms = {d.code: d.name for d in db.query(SkillDomain).all()}
    dims = (db.query(SkillDimension)
            .order_by(SkillDimension.domain_code, SkillDimension.order_index).all())
    toggled = {t.dimension_code: bool(t.enabled) for t in db.query(CourseDimensionToggle)
               .filter(CourseDimensionToggle.course_id == course_id).all()}
    rows = []
    for d in dims:
        enabled = bool(d.enabled) and toggled.get(d.code, True)
        rows.append({"code": d.code, "name": d.name,
                     "domain_code": d.domain_code,
                     "domain_label": doms.get(d.domain_code, d.domain_code),
                     "enabled": enabled, "disabled": not enabled})
    return rows, doms


@router.get("/courses/{course_id}/dimensions")
def course_dimensions(course_id: int,
                      cur: CurrentUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "课程不存在")
    rows, _doms = _dimension_rows(db, course_id)
    disabled = [r["code"] for r in rows if r["disabled"]]
    return {"course_id": course_id, "disabled": disabled, "dimensions": rows,
            "total": len(rows), "disabled_count": len(disabled)}


class DimensionsBody(BaseModel):
    disabled: list[str] = []    # 本次提交的停用维度 code 全集(其余自动恢复启用)


@router.put("/courses/{course_id}/dimensions")
def set_course_dimensions(course_id: int, body: DimensionsBody,
                          cur: CurrentUser = Depends(require_roles(*STAFF)),
                          db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "课程不存在")
    valid = {c[0] for c in db.query(SkillDimension.code).all()}
    unknown = [code for code in body.disabled if code not in valid]
    if unknown:
        raise HTTPException(422, f"未知能力维度: {unknown}")
    # 全量重置: 停用行写 enabled=False(absent=启用), 不再停用的旧行删除
    db.query(CourseDimensionToggle).filter(
        CourseDimensionToggle.course_id == course_id).delete(synchronize_session=False)
    for code in dict.fromkeys(body.disabled):
        db.add(CourseDimensionToggle(course_id=course_id, dimension_code=code,
                                     enabled=False))
    db.commit()
    rows, _doms = _dimension_rows(db, course_id)
    disabled = [r["code"] for r in rows if r["disabled"]]
    return {"course_id": course_id, "disabled": disabled, "dimensions": rows,
            "total": len(rows), "disabled_count": len(disabled)}
