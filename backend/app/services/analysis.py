"""
Session Analysis Service.

Pluggable analysis layer for evaluating a live session's movement data.

Architecture note:
    This module defines the contract for session analysis. The current MVP
    implementation uses joint-angle statistics (no ML required). When the
    full calibration + ST-GCN pipeline is ready, swap the internals of
    `analyze_session()` without changing its signature or return type.

    Future ML integration points are marked with "# ML-READY:" comments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from app.services.extraction import extract_landmarks_from_frames
from app.services.normalization import normalize_landmarks, compute_joint_angles

logger = logging.getLogger(__name__)

# ─── Response Contract ─────────────────────────────────────────────
# This dataclass IS the contract between the analysis layer and the
# WS handler / frontend. Keep it stable across MVP → ML transitions.


@dataclass
class JointSummary:
    """Analysis summary for a single joint."""
    joint_name: str
    mean_angle_degrees: float
    range_of_motion_degrees: float
    stability_score: float  # 0–1, higher = more consistent


@dataclass
class SessionFeedback:
    """Complete feedback for a finished session."""
    total_frames: int
    duration_seconds: float
    joint_summaries: list[JointSummary] = field(default_factory=list)
    overall_score: float = 0.0  # 0–100
    message: str = ""

    # ML-READY: Future fields for calibration-based evaluation.
    # These will be populated when the full pipeline is active.
    # The frontend should render them when present.
    passed: bool | None = None              # None = no calibration baseline yet
    distance_to_centroid: float | None = None
    calibration_available: bool = False


# Joint names corresponding to the angle triplets in normalization.py
_ANGLE_JOINT_NAMES = [
    "Right Elbow",
    "Right Shoulder",
    "Left Elbow",
    "Left Shoulder",
    "Right Knee",
    "Right Hip",
    "Left Knee",
    "Left Hip",
    "Hip Alignment",
    "Shoulder Alignment",
]


def analyze_session(
    frame_buffer: list[dict],
    fps: float = 30.0,
    # ML-READY: When calibration is available, pass these in:
    user_centroid: np.ndarray | None = None,
    model: object | None = None,
    threshold: float | None = None,
) -> SessionFeedback:
    """
    Analyze a completed session and return structured feedback.

    This is the single entry point for all session analysis. The WS handler
    calls this function; the internals can change without affecting callers.

    Args:
        frame_buffer: Raw WS frame dicts with 'landmarks' key.
        fps: Estimated frames per second for duration calculation.
        user_centroid: (ML-READY) User's calibrated centroid embedding.
        model: (ML-READY) Loaded ST-GCN model for inference.
        threshold: (ML-READY) Deviation threshold for pass/fail.

    Returns:
        SessionFeedback with kinematic analysis results.
    """
    total_frames = len(frame_buffer)
    duration = total_frames / fps if fps > 0 else 0.0

    if total_frames < 5:
        return SessionFeedback(
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            overall_score=0.0,
            message="Session too short for meaningful analysis. Try recording at least a few seconds.",
        )

    try:
        # ── Step 1: Convert raw WS frames → numpy array ──────────────
        landmarks = extract_landmarks_from_frames(frame_buffer)
        # landmarks shape: (T, 33, 4)

        # ── Step 2: Normalize for analysis ────────────────────────────
        normalized = normalize_landmarks(landmarks)
        # normalized shape: (1, 3, 64, 33)

        # ── Step 3: Compute joint angles from normalized coords ───────
        # Use the pre-normalized (but root-centered + scaled) coords
        coords_3d = landmarks[:, :, :3].copy()  # (T, 33, 3)
        angles = compute_joint_angles(coords_3d)
        # angles shape: (T, N_angles)

        # ── Step 4: Compute per-joint statistics ──────────────────────
        joint_summaries = _compute_joint_summaries(angles)

        # ── Step 5: Compute overall score ─────────────────────────────
        overall_score = _compute_overall_score(joint_summaries)

        # ML-READY: When calibration is available, run the full pipeline here:
        # if user_centroid is not None and model is not None:
        #     embedding = model.forward(normalized)
        #     distance = cosine_distance(embedding, user_centroid)
        #     passed = distance <= threshold
        #     # Could also run DTW fallback for joint-level error report
        #     return SessionFeedback(
        #         ..., passed=passed, distance_to_centroid=distance,
        #         calibration_available=True
        #     )

        message = _generate_feedback_message(overall_score, joint_summaries, duration)

        return SessionFeedback(
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            joint_summaries=joint_summaries,
            overall_score=round(overall_score, 1),
            message=message,
            calibration_available=False,
        )

    except Exception as e:
        logger.error(f"Session analysis failed: {e}", exc_info=True)
        return SessionFeedback(
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            overall_score=0.0,
            message=f"Analysis encountered an error: {str(e)}. Raw frame data was still captured.",
        )


def _compute_joint_summaries(angles: np.ndarray) -> list[JointSummary]:
    """Compute per-joint statistics from angle time series."""
    summaries = []

    for i, name in enumerate(_ANGLE_JOINT_NAMES):
        if i >= angles.shape[1]:
            break

        joint_angles = np.degrees(angles[:, i])  # Convert radians → degrees

        mean_angle = float(np.mean(joint_angles))
        angle_range = float(np.max(joint_angles) - np.min(joint_angles))
        std_dev = float(np.std(joint_angles))

        # Stability: inverse of normalized std deviation.
        # A perfectly still joint → stability = 1.0
        # A wildly varying joint → stability → 0.0
        # Normalize by dividing std by the range (if any); cap at 1.0
        if angle_range > 1e-3:
            stability = max(0.0, min(1.0, 1.0 - (std_dev / (angle_range + 1e-6))))
        else:
            stability = 1.0  # No movement → perfectly stable

        summaries.append(JointSummary(
            joint_name=name,
            mean_angle_degrees=round(mean_angle, 1),
            range_of_motion_degrees=round(angle_range, 1),
            stability_score=round(stability, 3),
        ))

    return summaries


def _compute_overall_score(summaries: list[JointSummary]) -> float:
    """
    Compute an overall movement quality score (0–100).

    MVP heuristic based on stability scores across all joints.
    ML-READY: Replace with calibration-based pass/fail distance.
    """
    if not summaries:
        return 0.0

    avg_stability = np.mean([s.stability_score for s in summaries])

    # Scale stability (0–1) to a 0–100 score with a slight curve
    # to make typical movements score in a useful range
    score = avg_stability * 100.0

    return float(np.clip(score, 0.0, 100.0))


def _generate_feedback_message(
    score: float,
    summaries: list[JointSummary],
    duration: float,
) -> str:
    """Generate a human-readable summary message."""
    if score >= 80:
        quality = "Excellent movement consistency"
    elif score >= 60:
        quality = "Good movement consistency"
    elif score >= 40:
        quality = "Moderate movement consistency"
    else:
        quality = "Movement was highly variable"

    # Find the most and least stable joints
    if summaries:
        sorted_by_stability = sorted(summaries, key=lambda s: s.stability_score)
        least_stable = sorted_by_stability[0]
        most_stable = sorted_by_stability[-1]

        detail = (
            f"{quality} across {len(summaries)} tracked joints over {duration:.1f}s. "
            f"Most consistent: {most_stable.joint_name} "
            f"(stability {most_stable.stability_score:.0%}). "
            f"Needs attention: {least_stable.joint_name} "
            f"(stability {least_stable.stability_score:.0%}, "
            f"range {least_stable.range_of_motion_degrees:.0f}°)."
        )
    else:
        detail = f"{quality}. Session lasted {duration:.1f}s."

    return detail
