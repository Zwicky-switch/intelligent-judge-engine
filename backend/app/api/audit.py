"""审计日志(不可删除): 管理员查看."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.constants import ROLE_ADMIN
from app.core.deps import CurrentUser, require_roles
from app.db import get_db
from app.models import AuditLog

from app.api.serializers import audit_dict

router = APIRouter(prefix="/audit", tags=["审计"])


@router.get("")
def list_audit(action: str | None = None, limit: int = Query(default=200, le=1000),
               cur: CurrentUser = Depends(require_roles(ROLE_ADMIN)),
               db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {"items": [audit_dict(a) for a in rows], "total": len(rows)}
