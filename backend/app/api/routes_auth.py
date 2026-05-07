"""
Basic auth routes for app-level username/password accounts (MVP).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException

from app.db.queries import create_app_user, ensure_user_profile, get_app_user_by_username
from app.db.supabase_client import get_supabase_client
from app.utils.schemas import (
    AuthUserResponse,
    LoginUserRequest,
    RegisterUserRequest,
)

router = APIRouter()

logger = logging.getLogger(__name__)

# In-memory fallback so local dev can still proceed if Supabase is unavailable.
_local_users: dict[str, dict] = {}


def _safe_delete_auth_user(user_id: str) -> bool:
    """Best-effort rollback for partially-created Supabase auth users."""
    try:
        client = get_supabase_client()
        client.auth.admin.delete_user(user_id)
        return True
    except Exception as e:
        logger.warning("Auth user rollback failed for %s: %s", user_id, e)
        return False


def _is_duplicate_username_error(exc: BaseException) -> bool:
    """Detect Postgres UNIQUE / duplicate insert from nested client exceptions."""
    parts: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(repr(cur))
        parts.append(str(cur))
        cur = cur.__cause__ or cur.__context__

    hay = " ".join(parts).lower()
    needles = (
        "23505",
        "unique constraint",
        "duplicate key",
        "already exists",
        "app_users_username_key",
    )
    return any(n in hay for n in needles)


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

    if username in _local_users:
        raise HTTPException(status_code=409, detail="Username is already taken.")

    password_hash = _hash_password(request.password)

    # Prefer Supabase persistence.
    provisioned_auth_user_id: str | None = None
    try:
        existing = await get_app_user_by_username(username)
        if existing:
            raise HTTPException(status_code=409, detail="Username is already taken.")

        auth_user_id = None
        # Try to provision a matching Supabase auth.users row so FK-linked
        # profile/calibration tables can persist by this user_id.
        try:
            client = get_supabase_client()
            auth_user = client.auth.admin.create_user(
                {
                    "email": f"{username}@pke.local",
                    "password": request.password,
                    "email_confirm": True,
                }
            )
            auth_user_id = getattr(getattr(auth_user, "user", None), "id", None)
            provisioned_auth_user_id = auth_user_id
        except Exception as e:
            logger.warning("Auth user provision failed; using app_users-only id: %s", e)

        created = await create_app_user(
            username=username,
            password_hash=password_hash,
            user_id=auth_user_id,
        )
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
    except Exception as e:
        if _is_duplicate_username_error(e):
            raise HTTPException(status_code=409, detail="Username is already taken.")

        if provisioned_auth_user_id:
            rolled_back = _safe_delete_auth_user(provisioned_auth_user_id)
            if not rolled_back:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Registration failed after provisioning auth user and rollback failed. "
                        "Manual cleanup may be required."
                    ),
                ) from e

        logger.warning("Supabase register failed; using in-memory fallback: %s", e)

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
        # Backfill profile row for legacy users so FK-dependent flows (calibration)
        # can persist sessions/centroids reliably.
        try:
            await ensure_user_profile(user_id=user["id"], display_name=user["username"])
        except Exception as e:
            logger.warning("Unable to ensure profile for existing user %s: %s", user["id"], e)
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
