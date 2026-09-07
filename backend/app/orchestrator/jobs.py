"""批量评阅任务: 后台线程执行, 进度/统计入库."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Answer, AssessmentJob
from app.orchestrator.runner import default_llm, grade_answers_batch

logger = logging.getLogger(__name__)


def _collect_ids(db: Session, scope: dict) -> list[int]:
    q = db.query(Answer)
    kind = scope.get("kind", "all_pending")
    if kind == "ids":
        return [int(x) for x in scope.get("answer_ids", [])]
    if kind == "student":
        q = q.filter(Answer.student_token == scope["student_token"], Answer.graded.is_(False))
    elif kind == "item":
        q = q.filter(Answer.item_id == int(scope["item_id"]), Answer.graded.is_(False))
    else:  # all_pending / seed
        q = q.filter(Answer.graded.is_(False))
    return [r.id for r in q.all()]


def _run(job_id: int):
    db: Session = SessionLocal()
    try:
        job = db.get(AssessmentJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        ids = _collect_ids(db, job.scope or {})
        llm = default_llm()
        stats = grade_answers_batch(db, ids, llm=llm)

        job = db.get(AssessmentJob, job_id)
        job.status = "done"
        job.stats = stats
        job.error = ""
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("任务 %s 失败", job_id)
        try:
            job = db.get(AssessmentJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(e)[:400]
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def create_and_launch(scope: dict) -> int:
    db = SessionLocal()
    job = AssessmentJob(scope=scope, status="pending")
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    t = threading.Thread(target=_run, args=(job_id,), daemon=True)
    t.start()
    return job_id
