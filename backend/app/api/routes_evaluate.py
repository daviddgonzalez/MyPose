"""
Evaluation Routes.

Accepts a movement sequence and evaluates it against
the user's calibrated baseline.
"""

from __future__ import annotations

import json
import logging
import uuid

import numpy as np
from fastapi import APIRouter, Request

from app.config import settings
from app.db.queries import (
    get_closest_calibration_sequence,
    get_exercise_by_name,
    get_user_centroid,
    store_evaluation,
)
from app.ml.dtw_fallback import compute_joint_errors
from app.services.extraction import frames_to_array
from app.services.normalization import normalize_landmarks
from app.utils.schemas import (
    EvaluationRequest,
    EvaluationResponse,
    JointError,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def run_evaluation(
    user_id: str,
    exercise_name: str,
    landmarks_arr: np.ndarray,
    model: object,
) -> EvaluationResponse:
    """
    Core evaluation pipeline. Shared by /evaluate and the upload background task.

    Args:
        user_id, exercise_name: identify the user's centroid to compare against.
        landmarks_arr: (T, 33, 4) raw landmarks.
        model: loaded PKEModel (must not be None).

    Returns: a fully-populated EvaluationResponse. Persists to Supabase on success.
    """
    evaluation_id = str(uuid.uuid4())
    threshold = settings.deviation_threshold

    exercise = await get_exercise_by_name(exercise_name)
    if exercise is None:
        return EvaluationResponse(
            evaluation_id=evaluation_id,
            passed=False,
            distance_to_centroid=0.0,
            threshold=threshold,
            joint_errors=[],
            dtw_triggered=False,
            message=f"Unknown exercise '{exercise_name}'.",
        )

    centroid_record = await get_user_centroid(
        user_id=user_id,
        exercise_id=exercise["id"],
    )
    if centroid_record is None:
        return EvaluationResponse(
            evaluation_id=evaluation_id,
            passed=False,
            distance_to_centroid=0.0,
            threshold=threshold,
            joint_errors=[],
            dtw_triggered=False,
            message="User has not calibrated for this exercise.",
        )

    centroid_raw = centroid_record["centroid"]
    if isinstance(centroid_raw, str):
        centroid_raw = json.loads(centroid_raw)
    centroid = np.asarray(centroid_raw, dtype=np.float32)
    threshold = centroid_record.get("threshold") or settings.deviation_threshold

    # Normalize → embed → cosine distance (matches services/analysis.py:144-152).
    normalized = normalize_landmarks(landmarks_arr, sequence_length=64)
    try:
        embedding = model.embed(normalized)[0]  # (256,)
    except Exception as e:
        logger.warning(f"Embedding failed during /evaluate: {e}")
        return EvaluationResponse(
            evaluation_id=evaluation_id,
            passed=False,
            distance_to_centroid=0.0,
            threshold=threshold,
            joint_errors=[],
            dtw_triggered=False,
            message=f"Embedding failed: {e}",
        )

    distance = float(1.0 - np.dot(embedding, centroid))
    passed = distance <= threshold

    joint_errors: list[JointError] = []
    dtw_triggered = False
    dtw_details: dict | None = None

    if not passed:
        try:
            ref_row = await get_closest_calibration_sequence(
                user_id=user_id,
                exercise_id=exercise["id"],
                query_embedding=embedding.tolist(),
            )
            if ref_row and ref_row.get("landmarks_json"):
                ref_frames = ref_row["landmarks_json"]
                if isinstance(ref_frames, str):
                    ref_frames = json.loads(ref_frames)
                # landmarks_json was stored as [frame.model_dump(), ...] in
                # routes_calibration.py:225. Reconstruct (T, 33, 3) coords.
                ref_coords = _landmarks_json_to_coords(ref_frames)
                query_coords = landmarks_arr[:, :, :3].astype(np.float32)
                joint_dicts, dtw_cost, dtw_ok = compute_joint_errors(
                    query_coords, ref_coords
                )
                if dtw_ok:
                    joint_errors = [JointError(**jd) for jd in joint_dicts]
                    dtw_triggered = True
                    dtw_details = {
                        "cost": dtw_cost,
                        "reference_sequence_id": ref_row.get("id"),
                    }
        except Exception as e:
            logger.warning(f"DTW fallback failed (non-fatal): {e}")

    try:
        await store_evaluation(
            evaluation_id=evaluation_id,
            user_id=user_id,
            exercise_id=exercise["id"],
            embedding=embedding.tolist(),
            distance_to_centroid=distance,
            passed=passed,
            joint_errors=[je.model_dump() for je in joint_errors] or None,
            dtw_details=dtw_details,
        )
    except Exception as e:
        logger.warning(f"Failed to persist evaluation row: {e}")

    return EvaluationResponse(
        evaluation_id=evaluation_id,
        passed=passed,
        distance_to_centroid=distance,
        threshold=threshold,
        joint_errors=joint_errors,
        dtw_triggered=dtw_triggered,
        message="Movement evaluated." if passed else "Movement deviates from baseline.",
    )


def _landmarks_json_to_coords(landmarks_json: list[dict]) -> np.ndarray:
    """Reconstruct (T, 33, 3) coords from the JSON shape stored by calibration."""
    out = []
    for frame in landmarks_json:
        lms = frame.get("landmarks", [])
        out.append([[lm["x"], lm["y"], lm["z"]] for lm in lms])
    return np.array(out, dtype=np.float32)


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_movement(request: EvaluationRequest, http_request: Request):
    """
    Evaluate a movement sequence against the user's calibrated profile.

    Pipeline:
    1. Normalize the incoming landmarks (root-center, scale-invariant).
    2. Generate embedding via user-calibrated ST-GCN.
    3. Compare embedding to user's centroid (cosine distance).
    4. If distance > threshold → run DTW fallback for joint-level error report.
    """
    model = getattr(http_request.app.state, "model", None)
    if model is None:
        return EvaluationResponse(
            evaluation_id=str(uuid.uuid4()),
            passed=False,
            distance_to_centroid=0.0,
            threshold=settings.deviation_threshold,
            joint_errors=[],
            dtw_triggered=False,
            message="Model not loaded on server.",
        )

    landmarks_arr = frames_to_array(request.landmarks)
    return await run_evaluation(
        user_id=request.user_id,
        exercise_name=request.exercise_name,
        landmarks_arr=landmarks_arr,
        model=model,
    )
