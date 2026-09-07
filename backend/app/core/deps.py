"""FastAPI 依赖: 当前用户解析与角色守卫."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user: User, payload: dict):
        self.user = user
        self.id = user.id
        self.username = user.username
        self.display_name = user.display_name
        self.role = user.role
        self.student_token = user.student_token
        self.payload = payload


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或凭证缺失")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "凭证无效或已过期")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已停用")
    return CurrentUser(user, payload)


def require_roles(*roles: str):
    """工厂: 返回依赖, 校验角色集合."""

    def dep(cur: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if cur.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无此操作权限")
        return cur

    return dep


def get_student_or_any(cur: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """学生只能访问本人, 教师/管理员可访问任意学生."""
    return cur
