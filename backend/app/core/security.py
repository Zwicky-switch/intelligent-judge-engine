"""口令哈希(pbkdf2, 标准库)与 JWT 签发/校验."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone

import jwt

from app.config import settings

PBKDF2_ITER = 120_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """返回 (salt_hex, hash) 由调用方拼接存储."""
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITER
    )
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITER
    )
    return hmac.compare_digest(dk.hex(), expected_hash)


def create_access_token(user_id: int, username: str, role: str, student_token: str | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "student_token": student_token,
        "iat": now,
        "exp": now + int(settings.TOKEN_TTL_HOURS) * 3600,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()
