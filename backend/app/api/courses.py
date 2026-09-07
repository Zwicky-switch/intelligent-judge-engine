"""课程浏览(供登录用户选课/命题/看板)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.constants import ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER
from app.core.deps import CurrentUser, get_current_user, require_roles
from app.db import get_db
from app.models import Chapter, Course, Item, User

router = APIRouter(prefix="/courses", tags=["课程"])


def _course_dict(db: Session, c: Course) -> dict:
    ch_count = db.query(Chapter).filter(Chapter.course_id == c.id).count()
    it_count = db.query(Item).filter(Item.course_id == c.id).count()
    stu_count = (db.query(User).filter(User.course_id == c.id, User.role == "student").count())
    # 学生参与度: 有成绩记录的学生数
    return {"id": c.id, "code": c.code, "name": c.name, "description": c.description,
            "active": bool(c.active),
            "chapter_count": ch_count, "item_count": it_count,
            "student_count": stu_count}


@router.get("")
def list_courses(cur: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    courses = db.query(Course).order_by(Course.code).all()
    return {"items": [_course_dict(db, c) for c in courses], "total": len(courses)}


@router.get("/{course_id}")
def course_detail(course_id: int, cur: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(404, "课程不存在")
    return _course_dict(db, c)


@router.post("")
def create_course(body: dict, cur: CurrentUser = Depends(
        require_roles(ROLE_ADMIN, ROLE_PROP_TEACHER)), db: Session = Depends(get_db)):
    code = str(body.get("code") or "").strip()
    name = str(body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(422, "code/name 必填")
    if db.query(Course).filter(Course.code == code).first():
        raise HTTPException(409, "课程代码已存在")
    c = Course(code=code, name=name, description=str(body.get("description") or ""))
    db.add(c)
    db.commit()
    return _course_dict(db, c)
