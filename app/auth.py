"""
auth.py — Password hashing, user creation, authentication.
"""

import bcrypt

from app import timeutil
from app.db import get_db, get_user_by_username


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_user(username: str, password: str, global_role: str = "user") -> int:
    db = get_db()
    result = db["users"].insert({
        "username": username,
        "password_hash": hash_password(password),
        "global_role": global_role,
        "created_at": timeutil.now_iso(),
    })
    assert result.last_pk is not None
    return int(result.last_pk)


def authenticate(username: str, password: str):
    db = get_db()
    user = get_user_by_username(db, username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None
