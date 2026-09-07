"""认证: 登录 / 当前用户."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user
from app.core.security import create_access_token, verify_password
from app.db import get_db
from app.models import User

from app.api.serializers import user_dict

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == body.username.strip()).first()
    if u is None or not u.active or not verify_password(body.password, u.salt, u.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = create_access_token(u.id, u.username, u.role, u.student_token)
    return {"access_token": token, "token_type": "bearer", "user": user_dict(u)}


@router.get("/me")
def me(cur: CurrentUser = Depends(get_current_user)):
    return user_dict(cur.user)
