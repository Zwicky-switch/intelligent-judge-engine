"""批量评阅任务: 触发(异步后台)与查询."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constants import ROLE_ADMIN, ROLE_GRADER, ROLE_PROP_TEACHER
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.models import AssessmentJob
from app.orchestrator.jobs import create_and_launch

router = APIRouter(prefix="/assessments", tags=["批量评阅"])
STAFF = (ROLE_ADMIN, ROLE_PROP_TEACHER, ROLE_GRADER)


class RunScope(BaseModel):
    kind: str = "all_pending"   # all_pending / student / item / ids
    student_token: str | None = None
    item_id: int | None = None
    answer_ids: list[int] = []


@router.post("/run")
def run_assessment(scope: RunScope, cur: CurrentUser = Depends(require_roles(*STAFF)),
                   db: Session = Depends(get_db)):
    # 立即校验 scope, 避免异步任务才发现参数错误
    if scope.kind == "student" and not scope.student_token:
        raise HTTPException(422, "student scope 需要 student_token")
    if scope.kind == "item" and scope.item_id is None:
        raise HTTPException(422, "item scope 需要 item_id")
    job_id = create_and_launch(scope.dict())
    return {"job_id": job_id, "status": "pending"}


@router.get("/{job_id}")
def get_job(job_id: int, cur: CurrentUser = Depends(require_roles(*STAFF)),
            db: Session = Depends(get_db)):
    job = db.get(AssessmentJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return {
        "id": job.id, "status": job.status, "scope": job.scope or {},
        "stats": job.stats or {}, "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
