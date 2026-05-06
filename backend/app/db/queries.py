"""
Database query functions for pgvector embedding operations.

Handles storing and retrieving embeddings, centroids, and evaluation results
from Supabase PostgreSQL with pgvector.
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime, timedelta, timezone

from app.db.supabase_client import get_supabase_client


async def get_exercise_by_name(name: str) -> Optional[dict]:
    """Look up an exercise row by canonical name."""
    client = get_supabase_client()
    result = (
        client.table("exercises")
        .select("id,name")
        .eq("name", name)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def create_calibration_session(
    session_id: str,
    user_id: str,
    exercise_id: str,
    status: str = "pending",
) -> Optional[dict]:
    """Create a calibration session row."""
    client = get_supabase_client()
    result = (
        client.table("calibration_sessions")
        .insert(
            {
                "id": session_id,
                "user_id": user_id,
                "exercise_id": exercise_id,
                "status": status,
            }
        )
        .execute()
    )
    return result.data[0] if result.data else None


async def update_calibration_session_status(session_id: str, status: str) -> None:
    """Update the status of a calibration session."""
    client = get_supabase_client()
    (
        client.table("calibration_sessions")
        .update({"status": status})
        .eq("id", session_id)
        .execute()
    )


async def store_calibration_embedding(
    sequence_id: str,
    session_id: str,
    embedding: list[float],
    landmarks_json: Optional[dict] = None,
    storage_path: Optional[str] = None,
) -> dict:
    """Store a calibration sequence embedding in the database."""
    client = get_supabase_client()
    result = (
        client.table("calibration_sequences")
        .upsert({
            "id": sequence_id,
            "session_id": session_id,
            "embedding": embedding,
            "landmarks_json": landmarks_json,
            "storage_path": storage_path,
        })
        .execute()
    )
    return result.data[0] if result.data else {}


async def compute_and_store_centroid(
    user_id: str,
    exercise_id: str,
    session_id: str,
    model_version: str = "v0.1",
) -> dict:
    """
    Compute the mean embedding (centroid) from all calibration sequences
    in a session and store it in calibration_centroids.

    Uses a PostgreSQL function for server-side averaging of vector columns.
    """
    client = get_supabase_client()

    # Fetch all embeddings for the session
    sequences = (
        client.table("calibration_sequences")
        .select("embedding")
        .eq("session_id", session_id)
        .not_.is_("embedding", "null")
        .execute()
    )

    if not sequences.data:
        raise ValueError(f"No embeddings found for session {session_id}")

    # Compute centroid (mean of all embeddings)
    embeddings = [seq["embedding"] for seq in sequences.data]
    num_embeddings = len(embeddings)
    dim = len(embeddings[0])

    centroid = [
        sum(emb[i] for emb in embeddings) / num_embeddings
        for i in range(dim)
    ]

    # Upsert centroid (one per user+exercise pair)
    result = (
        client.table("calibration_centroids")
        .upsert(
            {
                "user_id": user_id,
                "exercise_id": exercise_id,
                "centroid": centroid,
                "model_version": model_version,
            },
            on_conflict="user_id,exercise_id",
        )
        .execute()
    )

    return result.data[0] if result.data else {}


async def get_user_centroid(
    user_id: str,
    exercise_id: str,
) -> Optional[dict]:
    """
    Retrieve the user's calibration centroid for a specific exercise.

    Returns the centroid vector and threshold, or None if not calibrated.
    """
    client = get_supabase_client()
    result = (
        client.table("calibration_centroids")
        .select("centroid, threshold, model_version")
        .eq("user_id", user_id)
        .eq("exercise_id", exercise_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def store_evaluation(
    evaluation_id: str,
    user_id: str,
    exercise_id: str,
    embedding: list[float],
    distance_to_centroid: float,
    passed: bool,
    joint_errors: Optional[dict] = None,
    dtw_details: Optional[dict] = None,
) -> dict:
    """Store an evaluation result in the database."""
    client = get_supabase_client()
    result = (
        client.table("evaluations")
        .insert({
            "id": evaluation_id,
            "user_id": user_id,
            "exercise_id": exercise_id,
            "embedding": embedding,
            "distance_to_centroid": distance_to_centroid,
            "passed": passed,
            "joint_errors": joint_errors,
            "dtw_details": dtw_details,
        })
        .execute()
    )
    return result.data[0] if result.data else {}


async def get_closest_calibration_sequence(
    user_id: str,
    exercise_id: str,
    query_embedding: list[float],
) -> Optional[dict]:
    """
    Find the calibration sequence closest to the query embedding.

    Uses pgvector's cosine distance operator (<=>).
    Called during DTW fallback to find the best calibration rep to compare against.
    """
    client = get_supabase_client()

    # Use Supabase RPC to call a custom function for vector similarity search
    result = client.rpc(
        "match_calibration_sequence",
        {
            "query_embedding": query_embedding,
            "target_user_id": user_id,
            "target_exercise_id": exercise_id,
            "match_count": 1,
        },
    ).execute()

    return result.data[0] if result.data else None


async def create_progress_checkin(
    user_id: str,
    exercise_id: str,
    reps_completed: int,
    average_quality_score: float,
    passed_reps: int = 0,
    failed_reps: int = 0,
    duration_seconds: Optional[float] = None,
    notes: str = "",
) -> dict:
    """Persist a workout progress check-in row."""
    client = get_supabase_client()
    payload = {
        "user_id": user_id,
        "exercise_id": exercise_id,
        "reps_completed": reps_completed,
        "average_quality_score": average_quality_score,
        "passed_reps": passed_reps,
        "failed_reps": failed_reps,
        "duration_seconds": duration_seconds,
        "notes": notes,
    }
    result = client.table("progress_checkins").insert(payload).execute()
    return result.data[0] if result.data else {}


async def list_progress_checkins(
    user_id: str,
    exercise_id: str,
    days: int = 14,
) -> list[dict]:
    """Fetch recent progress check-ins for trend aggregation."""
    client = get_supabase_client()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = (
        client.table("progress_checkins")
        .select("id,reps_completed,average_quality_score,created_at")
        .eq("user_id", user_id)
        .eq("exercise_id", exercise_id)
        .gte("created_at", since.isoformat())
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


async def get_app_user_by_username(username: str) -> Optional[dict]:
    """Fetch app user row by username."""
    client = get_supabase_client()
    result = (
        client.table("app_users")
        .select("id,username,password_hash")
        .eq("username", username)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def create_app_user(username: str, password_hash: str) -> dict:
    """Create a new app user with hashed password."""
    client = get_supabase_client()
    result = (
        client.table("app_users")
        .insert({
            "username": username,
            "password_hash": password_hash,
        })
        .execute()
    )
    return result.data[0] if result.data else {}


async def ensure_user_profile(user_id: str, display_name: str = "") -> dict:
    """Ensure a matching user_profiles row exists for app-level auth user id."""
    client = get_supabase_client()
    result = (
        client.table("user_profiles")
        .upsert(
            {
                "id": user_id,
                "display_name": display_name,
            }
        )
        .execute()
    )
    return result.data[0] if result.data else {}
