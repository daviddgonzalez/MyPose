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
from app.services.strictness import get_profile, get_rom_target, StrictnessProfile
from app.config import settings

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
    combined_score: float = 0.0  # 0–1, min of stability and ROM ratio; agrees with `passed`
    passed: bool = True
    issues: list[str] = field(default_factory=list)


@dataclass
class SessionFeedback:
    """Complete feedback for a finished session."""
    strictness_level: str
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
    strictness: str = settings.default_strictness,
    exercise_name: str = "squat",
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
            strictness_level=strictness,
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            overall_score=0.0,
            message="Session too short for meaningful analysis. Try recording at least a few seconds.",
        )

    profile = get_profile(strictness)

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
        joint_summaries = _compute_joint_summaries(angles, profile, exercise_name)

        # ── Step 5: Compute heuristic score ───────────────────────────
        heuristic_score = _compute_overall_score(joint_summaries, profile, exercise_name)

        # ── Step 6: ML personal-match evaluation (when calibration exists) ──
        # The personal match is *not* blended into the overall score. The
        # Textbook score (heuristic) answers "is this textbook form?"; the
        # Personal match badge answers a separate question — "does this match
        # YOUR baseline?". Blending them produces a number that means neither.
        ml_passed = None
        ml_distance = None
        calibration_available = False

        if user_centroid is not None and model is not None:
            try:
                embedding = model.embed(normalized)  # (1, embedding_dim)
                emb_vec = embedding[0]
                dot = float(np.dot(emb_vec, user_centroid))
                ml_distance = float(1.0 - dot)

                effective_threshold = threshold if threshold is not None else settings.deviation_threshold
                ml_passed = ml_distance <= effective_threshold
                calibration_available = True
                logger.info(
                    f"Personal match: distance={ml_distance:.4f}, "
                    f"threshold={effective_threshold:.4f}, passed={ml_passed}"
                )
            except Exception as e:
                logger.warning(f"Personal-match embedding failed: {e}")

        overall_score = heuristic_score
        message = _generate_feedback_message(overall_score, joint_summaries, duration)

        return SessionFeedback(
            strictness_level=profile.level.value,
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            joint_summaries=joint_summaries,
            overall_score=round(overall_score, 1),
            message=message,
            passed=ml_passed,
            distance_to_centroid=ml_distance,
            calibration_available=calibration_available,
        )

    except Exception as e:
        logger.error(f"Session analysis failed: {e}", exc_info=True)
        return SessionFeedback(
            strictness_level=strictness,
            total_frames=total_frames,
            duration_seconds=round(duration, 1),
            overall_score=0.0,
            message=f"Analysis encountered an error: {str(e)}. Raw frame data was still captured.",
        )


def _compute_joint_summaries(angles: np.ndarray, profile: StrictnessProfile, exercise: str) -> list[JointSummary]:
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
        if angle_range > 1e-3:
            stability = max(0.0, min(1.0, 1.0 - (std_dev / (angle_range + 1e-6))))
        else:
            stability = 1.0  # No movement → perfectly stable

        # Evaluate Pass/Fail
        passed = True
        issues = []
        
        if stability < profile.min_stability_threshold:
            passed = False
            issues.append(f"Inconsistent stability (score: {stability:.2f})")
            
        target_rom = get_rom_target(exercise, name, profile)
        rom_ratio = 1.0
        if target_rom > 0:
            rom_ratio = min(1.0, angle_range / target_rom)
            if angle_range < target_rom:
                passed = False
                issues.append(f"Insufficient ROM ({angle_range:.0f}° / target {target_rom:.0f}°)")

        # Combined score: the bottleneck dimension drags the display down so a
        # joint's bar agrees with its pass/fail border.
        combined = min(stability, rom_ratio) if target_rom > 0 else stability

        summaries.append(JointSummary(
            joint_name=name,
            mean_angle_degrees=round(mean_angle, 1),
            range_of_motion_degrees=round(angle_range, 1),
            stability_score=round(stability, 3),
            combined_score=round(combined, 3),
            passed=passed,
            issues=issues
        ))

    return summaries


def _compute_overall_score(summaries: list[JointSummary], profile: StrictnessProfile, exercise: str) -> float:
    """
    Compute an overall movement quality score (0–100) combining stability and ROM.
    """
    if not summaries:
        return 0.0

    # 1. Stability Component
    stabilities = [s.stability_score for s in summaries]
    # Penalize low stabilities harder
    penalized = [s ** profile.penalty_curve_exponent for s in stabilities]
    stability_component = float(np.mean(penalized))

    # 2. ROM Component
    rom_passes = []
    for s in summaries:
        target = get_rom_target(exercise, s.joint_name, profile)
        if target > 0:
            ratio = s.range_of_motion_degrees / target
            rom_passes.append(min(1.0, ratio))
        else:
            # Does not apply or isometric
            rom_passes.append(1.0)
            
    rom_component = float(np.mean(rom_passes)) if rom_passes else 1.0

    # 3. Blended base score
    base_score = (profile.stability_weight * stability_component + 
                  profile.rom_weight * rom_component) * 100.0

    # 4. Final penalty for any joint that failed
    failed_count = sum(1 for s in summaries if not s.passed)
    penalty = failed_count * 5.0

    return float(np.clip(base_score - penalty, 0.0, 100.0))


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
