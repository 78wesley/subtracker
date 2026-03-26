"""
auth.py — Password hashing, user creation, authentication.
"""

import bcrypt
from database import get_db, get_user_by_username, init_db
import timeutil


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_user(username: str, password: str) -> int:
    db = get_db()
    result = db["users"].insert({
        "username": username,
        "password_hash": hash_password(password),
        "created_at": timeutil.now_iso(),
    })
    return result.last_pk


def authenticate(username: str, password: str):
    db = get_db()
    user = get_user_by_username(db, username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None
