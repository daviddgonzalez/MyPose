"""
Progress Tracking Routes.

Stores user progress check-ins and returns trend summaries for an exercise.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.db.queries import (
    create_progress_checkin,
    get_exercise_by_name,
    list_progress_checkins,
)
from app.utils.schemas import (
    ProgressCheckinRequest,
    ProgressCheckinResponse,
    ProgressSummaryResponse,
    ProgressTrendPoint,
)

router = APIRouter()

# Fallback store for local/dev use when DB is unavailable.
_progress_fallback: list[dict] = []
_known_exercises = {
    "squat",
    "deadlift",
    "lunge",
    "push_up",
    "plank",
    "overhead_press",
    "barbell_biceps_curl",
}


@router.post("/progress/checkin", response_model=ProgressCheckinResponse)
async def record_progress_checkin(request: ProgressCheckinRequest):
    """Record a workout checkpoint for user + exercise."""
    exercise_id: str | None = None
    try:
        exercise = await get_exercise_by_name(request.exercise_name)
    except Exception:
        exercise = None

    if exercise is not None:
        exercise_id = exercise["id"]
    elif request.exercise_name not in _known_exercises:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown exercise '{request.exercise_name}'.",
        )

    checkin_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    if exercise_id is not None:
        try:
            saved = await create_progress_checkin(
                user_id=request.user_id,
                exercise_id=exercise_id,
                reps_completed=request.reps_completed,
                average_quality_score=request.average_quality_score,
                passed_reps=request.passed_reps,
                failed_reps=request.failed_reps,
                duration_seconds=request.duration_seconds,
                notes=request.notes,
            )
            checkin_id = saved.get("id", checkin_id)
            created_at = saved.get("created_at", created_at)
        except Exception:
            _progress_fallback.append(
                {
                    "id": checkin_id,
                    "user_id": request.user_id,
                    "exercise_name": request.exercise_name,
                    "reps_completed": request.reps_completed,
                    "average_quality_score": request.average_quality_score,
                    "created_at": created_at,
                }
            )
    else:
        _progress_fallback.append(
            {
                "id": checkin_id,
                "user_id": request.user_id,
                "exercise_name": request.exercise_name,
                "reps_completed": request.reps_completed,
                "average_quality_score": request.average_quality_score,
                "created_at": created_at,
            }
        )

    return ProgressCheckinResponse(
        checkin_id=checkin_id,
        user_id=request.user_id,
        exercise_name=request.exercise_name,
        reps_completed=request.reps_completed,
        average_quality_score=request.average_quality_score,
        created_at=created_at,
    )


@router.get("/progress/summary", response_model=ProgressSummaryResponse)
async def get_progress_summary(
    user_id: str,
    exercise_name: str,
    days: int = Query(default=14, ge=1, le=365),
):
    """Return aggregate + daily trend points for recent progress."""
    exercise_id: str | None = None
    try:
        exercise = await get_exercise_by_name(exercise_name)
    except Exception:
        exercise = None

    if exercise is not None:
        exercise_id = exercise["id"]
    elif exercise_name not in _known_exercises:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown exercise '{exercise_name}'.",
        )

    rows: list[dict]
    if exercise_id is not None:
        try:
            rows = await list_progress_checkins(user_id=user_id, exercise_id=exercise_id, days=days)
        except Exception:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
            rows = [
                row for row in _progress_fallback
                if row["user_id"] == user_id
                and row["exercise_name"] == exercise_name
                and datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).timestamp() >= cutoff
            ]
    else:
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        rows = [
            row for row in _progress_fallback
            if row["user_id"] == user_id
            and row["exercise_name"] == exercise_name
            and datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).timestamp() >= cutoff
        ]

    totals = defaultdict(lambda: {"reps": 0, "quality_sum": 0.0, "count": 0})
    total_reps = 0
    total_quality_sum = 0.0

    for row in rows:
        date_key = row["created_at"][:10]
        reps = int(row["reps_completed"])
        quality = float(row["average_quality_score"])

        totals[date_key]["reps"] += reps
        totals[date_key]["quality_sum"] += quality
        totals[date_key]["count"] += 1

        total_reps += reps
        total_quality_sum += quality

    trend: list[ProgressTrendPoint] = []
    for date_key in sorted(totals.keys()):
        bucket = totals[date_key]
        trend.append(
            ProgressTrendPoint(
                date=date_key,
                total_reps=bucket["reps"],
                average_quality_score=(
                    bucket["quality_sum"] / bucket["count"] if bucket["count"] else 0.0
                ),
                checkins=bucket["count"],
            )
        )

    return ProgressSummaryResponse(
        user_id=user_id,
        exercise_name=exercise_name,
        days=days,
        total_reps=total_reps,
        average_quality_score=(total_quality_sum / len(rows) if rows else 0.0),
        total_checkins=len(rows),
        trend=trend,
    )
