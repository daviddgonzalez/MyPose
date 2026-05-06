"""
Basic auth routes for app-level username/password accounts (MVP).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid

from fastapi import APIRouter, HTTPException

from app.db.queries import create_app_user, ensure_user_profile, get_app_user_by_username
from app.utils.schemas import (
    AuthUserResponse,
    LoginUserRequest,
    RegisterUserRequest,
)

router = APIRouter()

# In-memory fallback so local dev can still proceed if Supabase is unavailable.
_local_users: dict[str, dict] = {}


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        salt_b64, hash_b64 = encoded_hash.split(":", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False

    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return hmac.compare_digest(computed, expected)


@router.post("/auth/register", response_model=AuthUserResponse)
async def register_user(request: RegisterUserRequest):
    username = request.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    password_hash = _hash_password(request.password)

    # Prefer Supabase persistence.
    try:
        existing = await get_app_user_by_username(username)
        if existing:
            raise HTTPException(status_code=409, detail="Username is already taken.")

        created = await create_app_user(username=username, password_hash=password_hash)
        user_id = created.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Unable to create user.")
        await ensure_user_profile(user_id=user_id, display_name=username)
        return AuthUserResponse(
            user_id=user_id,
            username=username,
            message="Account created.",
        )
    except HTTPException:
        raise
    except Exception:
        if username in _local_users:
            raise HTTPException(status_code=409, detail="Username is already taken.")
        user_id = str(uuid.uuid4())
        _local_users[username] = {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
        }
        return AuthUserResponse(
            user_id=user_id,
            username=username,
            message="Account created (local fallback).",
        )


@router.post("/auth/login", response_model=AuthUserResponse)
async def login_user(request: LoginUserRequest):
    username = request.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    try:
        user = await get_app_user_by_username(username)
        if not user or not _verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        return AuthUserResponse(
            user_id=user["id"],
            username=user["username"],
            message="Login successful.",
        )
    except HTTPException:
        raise
    except Exception:
        local_user = _local_users.get(username)
        if not local_user or not _verify_password(request.password, local_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        return AuthUserResponse(
            user_id=local_user["id"],
            username=local_user["username"],
            message="Login successful (local fallback).",
        )
