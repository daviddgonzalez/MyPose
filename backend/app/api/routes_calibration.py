"""
Calibration Routes.

Manages the user calibration lifecycle: create session → add sequences → finalize.
Uses in-memory storage for MVP. Swap for Supabase in production.
"""

from __future__ import annotations

import uuid
import logging

import numpy as np
from fastapi import APIRouter, HTTPException

from app.utils.schemas import (
    CalibrationFinalizeResponse,
    CalibrationSequenceRequest,
    CalibrationStartRequest,
    CalibrationStartResponse,
    CalibrationStatus,
)
from app.config import settings
from app.services.normalization import normalize_landmarks
from app.services.extraction import frames_to_array
from app.db.queries import (
    create_calibration_session,
    compute_and_store_centroid,
    get_exercise_by_name,
    store_calibration_embedding,
    update_calibration_session_status,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory session store (swap for Supabase in production)
_sessions: dict[str, dict] = {}


@router.post("/calibrate/start", response_model=CalibrationStartResponse)
async def start_calibration(request: CalibrationStartRequest):
    """
    Create a new calibration session for a user + exercise pair.

    The user will submit 3-5 sequences of correct form, after which
    the session is finalized to compute their personal baseline.
    """
    session_id = str(uuid.uuid4())
    exercise = await get_exercise_by_name(request.exercise_name)
    if exercise is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown exercise '{request.exercise_name}'. "
                "Use one of the seeded exercises in the catalog."
            ),
        )

    _sessions[session_id] = {
        "user_id": request.user_id,
        "exercise_name": request.exercise_name,
        "status": CalibrationStatus.PENDING,
        "sequences": [],
    }
    try:
        await create_calibration_session(
            session_id=session_id,
            user_id=request.user_id,
            exercise_id=exercise["id"],
            status=CalibrationStatus.PENDING.value,
        )
    except Exception as e:
        logger.warning(f"Unable to persist calibration session start: {e}")

    return CalibrationStartResponse(
        session_id=session_id,
        status=CalibrationStatus.PENDING,
        message=f"Calibration session created for '{request.exercise_name}'.",
    )


@router.post("/calibrate/{session_id}/sequence")
async def add_calibration_sequence(session_id: str, request: CalibrationSequenceRequest):
    """
    Add a single calibration sequence to an existing session.

    Accepts either raw landmarks (from live capture) or a Supabase Storage
    path (from video upload). 3-5 sequences are needed before finalization.
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    session = _sessions[session_id]

    if session["status"] == CalibrationStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Session already finalized.")

    if len(session["sequences"]) >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 calibration sequences allowed.")

    if not request.landmarks and not request.storage_path:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'landmarks' or 'storage_path'.",
        )

    sequence_id = str(uuid.uuid4())
    session["sequences"].append({
        "id": sequence_id,
        "landmarks": request.landmarks,
        "storage_path": request.storage_path,
    })

    return {
        "sequence_id": sequence_id,
        "session_id": session_id,
        "total_sequences": len(session["sequences"]),
        "message": f"Sequence added. {len(session['sequences'])}/5 recorded.",
    }


@router.post("/calibrate/{session_id}/finalize", response_model=CalibrationFinalizeResponse)
async def finalize_calibration(session_id: str):
    """
    Finalize the calibration session.

    This triggers:
    1. Normalization of all submitted sequences
    2. Embedding generation via the loaded ST-GCN model
    3. Few-shot fine-tuning of the projection head
    4. Centroid computation and in-memory storage
    """
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    session = _sessions[session_id]

    # Frontend gates on wall-clock duration (>=30s total, >=5s per take); the
    # backend re-checks total frame count as defense in depth in case a client
    # bypasses the UI. The frame floors assume a permissive 15fps minimum so
    # slower webcams aren't rejected: 5s -> 75 frames, 30s -> 450 frames.
    MIN_FRAMES_PER_SEQ = 75
    MIN_TOTAL_FRAMES = 450
    seq_frame_counts = [
        len(seq["landmarks"]) for seq in session["sequences"] if seq["landmarks"]
    ]
    total_frames = sum(seq_frame_counts)
    short_seqs = [n for n in seq_frame_counts if n < MIN_FRAMES_PER_SEQ]
    if total_frames < MIN_TOTAL_FRAMES or short_seqs:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Calibration data too short. Recorded {total_frames} frames across "
                f"{len(seq_frame_counts)} take(s); need at least {MIN_TOTAL_FRAMES} total "
                f"and {MIN_FRAMES_PER_SEQ} per take."
            ),
        )

    session["status"] = CalibrationStatus.PROCESSING
    try:
        await update_calibration_session_status(session_id, CalibrationStatus.PROCESSING.value)
    except Exception as e:
        logger.warning(f"Unable to persist calibration status=processing: {e}")

    # ── Get the model from app state ─────────────────────────────
    from fastapi import Request
    from starlette.requests import HTTPConnection

    # Access app state via the router — we import the model at call time
    # because the app isn't available at module load
    try:
        from app.main import app
        model = app.state.model
    except Exception:
        model = None

    if model is None:
        logger.warning("No model loaded — storing sequences but cannot compute centroid")
        return CalibrationFinalizeResponse(
            session_id=session_id,
            status=CalibrationStatus.FAILED,
            centroid_stored=False,
            num_sequences=len(session["sequences"]),
            message="Model not loaded. Cannot compute embeddings for calibration.",
        )

    # ── Convert stored sequences to numpy arrays ─────────────────
    raw_sequences: list[np.ndarray] = []
    for seq in session["sequences"]:
        if seq["landmarks"]:
            raw_sequences.append(frames_to_array(seq["landmarks"]))

    if len(raw_sequences) < 3:
        return CalibrationFinalizeResponse(
            session_id=session_id,
            status=CalibrationStatus.FAILED,
            centroid_stored=False,
            num_sequences=len(raw_sequences),
            message=f"Only {len(raw_sequences)} valid landmark sequences found.",
        )

    # ── Fine-tune projection head on user's sequences ────────────
    try:
        from app.ml.training import finetune, compute_centroid

        finetune(
            model=model,
            sequences=raw_sequences,
            lr=settings.finetune_lr,
            epochs=settings.finetune_epochs,
        )

        # ── Compute and store centroid ────────────────────────────
        centroid = compute_centroid(model, raw_sequences)

        from app.api.ws_live import store_centroid
        store_centroid(
            user_id=session["user_id"],
            exercise=session["exercise_name"],
            centroid=centroid,
            threshold=settings.deviation_threshold,
        )

        # Persist sequence embeddings + centroid in Supabase when available.
        try:
            exercise = await get_exercise_by_name(session["exercise_name"])
            if exercise:
                for seq, raw_seq in zip(session["sequences"], raw_sequences):
                    normalized = normalize_landmarks(raw_seq)
                    embedding = model.embed(normalized)[0].tolist()
                    landmarks_json = None
                    if seq["landmarks"]:
                        landmarks_json = [frame.model_dump() for frame in seq["landmarks"]]

                    await store_calibration_embedding(
                        sequence_id=seq["id"],
                        session_id=session_id,
                        embedding=embedding,
                        landmarks_json=landmarks_json,
                        storage_path=seq["storage_path"],
                    )

                await compute_and_store_centroid(
                    user_id=session["user_id"],
                    exercise_id=exercise["id"],
                    session_id=session_id,
                )
        except Exception as e:
            logger.warning(f"Unable to persist calibration embeddings/centroid: {e}")

        session["status"] = CalibrationStatus.COMPLETE
        try:
            await update_calibration_session_status(session_id, CalibrationStatus.COMPLETE.value)
        except Exception as e:
            logger.warning(f"Unable to persist calibration status=complete: {e}")

        return CalibrationFinalizeResponse(
            session_id=session_id,
            status=CalibrationStatus.COMPLETE,
            centroid_stored=True,
            num_sequences=len(raw_sequences),
            message=f"Calibration complete. Personal baseline stored for '{session['exercise_name']}'.",
        )

    except Exception as e:
        logger.error(f"Calibration pipeline failed: {e}", exc_info=True)
        session["status"] = CalibrationStatus.FAILED
        try:
            await update_calibration_session_status(session_id, CalibrationStatus.FAILED.value)
        except Exception as db_e:
            logger.warning(f"Unable to persist calibration status=failed: {db_e}")

        return CalibrationFinalizeResponse(
            session_id=session_id,
            status=CalibrationStatus.FAILED,
            centroid_stored=False,
            num_sequences=len(raw_sequences),
            message=f"Calibration failed: {str(e)}",
        )
