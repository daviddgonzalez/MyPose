"""
Path A: WebSocket Live Streaming Endpoint.

Receives real-time MediaPipe landmarks from the browser,
buffers into sliding windows, and returns per-rep evaluation results.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.analysis import analyze_session
from app.config import settings
from app.db.queries import get_exercise_by_name, get_user_centroid

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory centroid store — keyed by (user_id, exercise_name)
# Populated by the calibration finalize endpoint.
# In production, swap this for Supabase pgvector queries.
_centroid_store: dict[tuple[str, str], dict] = {}


def store_centroid(user_id: str, exercise: str, centroid: np.ndarray, threshold: float = 0.15) -> None:
    """Store a user's calibration centroid in memory."""
    _centroid_store[(user_id, exercise)] = {
        "centroid": centroid,
        "threshold": threshold,
    }
    logger.info(f"Centroid stored: user={user_id}, exercise={exercise}")


def get_centroid(user_id: str, exercise: str) -> dict | None:
    """Look up a user's calibration centroid. Returns None if not calibrated."""
    return _centroid_store.get((user_id, exercise))


@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Live landmark streaming endpoint.

    Protocol:
    - Client sends {"type": "config", "strictness": str, "exercise": str, "user_id": str}
    - Client sends JSON frames: {"type": "frame", "frame_idx": int, "landmarks": [[x,y,z], ...]}
    - Server buffers frames into a sliding window
    - Client sends {"type": "end"} to close the session
    - Server runs analysis on buffered frames and sends "session_feedback" + "session_end"
    """
    await websocket.accept()
    frame_buffer: list[dict] = []
    session_strictness = "moderate"
    session_exercise = "squat"
    session_user_id: str | None = None

    # Get the model from app state (may be None if no checkpoint)
    model = websocket.app.state.model

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)

            msg_type = message.get("type", "frame")

            if msg_type == "config":
                session_strictness = message.get("strictness", "moderate")
                session_exercise = message.get("exercise", "squat")
                session_user_id = message.get("user_id", None)
                logger.info(
                    f"Session configured: strictness={session_strictness}, "
                    f"exercise={session_exercise}, user_id={session_user_id}"
                )
                continue

            if msg_type == "end":
                # ── Look up user's calibration centroid ───────────────
                user_centroid = None
                threshold = settings.deviation_threshold

                if session_user_id and model is not None:
                    record = None
                    # Prefer persisted centroid from Supabase; fallback to in-memory.
                    try:
                        exercise = await get_exercise_by_name(session_exercise)
                        if exercise:
                            db_record = await get_user_centroid(
                                user_id=session_user_id,
                                exercise_id=exercise["id"],
                            )
                            if db_record:
                                record = {
                                    "centroid": np.array(db_record["centroid"], dtype=np.float32),
                                    "threshold": db_record.get("threshold", threshold),
                                }
                    except Exception as e:
                        logger.warning(f"Centroid DB lookup failed, falling back to memory: {e}")

                    if record is None:
                        record = get_centroid(session_user_id, session_exercise)
                    if record:
                        user_centroid = record["centroid"]
                        threshold = record.get("threshold", threshold)
                        logger.info(
                            f"Centroid found for user={session_user_id}, "
                            f"exercise={session_exercise}"
                        )
                    else:
                        logger.info(
                            f"No centroid for user={session_user_id}, "
                            f"exercise={session_exercise} — heuristic-only"
                        )

                # ── Run end-of-session analysis ──────────────────────
                feedback = analyze_session(
                    frame_buffer,
                    strictness=session_strictness,
                    exercise_name=session_exercise,
                    user_centroid=user_centroid,
                    model=model,
                    threshold=threshold,
                )

                # Send the feedback message (rich analysis data)
                feedback_dict = asdict(feedback)
                feedback_dict["type"] = "session_feedback"
                await websocket.send_json(feedback_dict)

                # Then send the session_end message (signals completion)
                await websocket.send_json({
                    "type": "session_end",
                    "total_frames": len(frame_buffer),
                    "message": "Session ended.",
                })
                break

            if msg_type == "frame":
                frame_buffer.append(message)

                # Send back an acknowledgement every 30 frames
                if len(frame_buffer) % 30 == 0:
                    await websocket.send_json({
                        "type": "ack",
                        "frames_received": len(frame_buffer),
                        "message": f"Buffered {len(frame_buffer)} frames.",
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected. Total frames: {len(frame_buffer)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
