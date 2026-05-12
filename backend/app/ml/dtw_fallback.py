"""
DTW fallback for per-joint error reports.

When the Siamese cosine distance exceeds the user's threshold, we fall back to
Dynamic Time Warping over joint-angle sequences to localize *which* joints
broke form. The actual DTW + angle math runs in the C++ extension `pke_cpp`
(see cpp/src/bindings.cpp); if the binary isn't importable we return an
empty result so the evaluation pipeline degrades gracefully to "distance-only".
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np

logger = logging.getLogger(__name__)

# JOINT_NAMES mirrors the angle ordering used in services/analysis.py:64-75
# and the C++ joint_angles.cpp implementation.
JOINT_NAMES = [
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

_CPP_BUILD_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "cpp", "build", "Release")
)

try:
    if _CPP_BUILD_DIR not in sys.path:
        sys.path.insert(0, _CPP_BUILD_DIR)
    import pke_cpp  # type: ignore
    _AVAILABLE = True
except ImportError as e:
    logger.warning(f"pke_cpp not available — DTW fallback disabled: {e}")
    pke_cpp = None  # type: ignore
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE


def compute_joint_errors(
    query_coords: np.ndarray,
    reference_coords: np.ndarray,
    band_width: int = 10,
) -> tuple[list[dict], float, bool]:
    """
    Compare two pose sequences and return per-joint angular error.

    Args:
        query_coords: (T_q, 33, 3) — the movement being evaluated.
        reference_coords: (T_r, 33, 3) — the user's calibrated reference.
        band_width: Sakoe-Chiba band for DTW (frames).

    Returns:
        (joint_errors, dtw_cost, ok). joint_errors is a list of dicts matching
        the JointError schema; ok=False means the C++ module wasn't loaded
        (joint_errors is empty in that case).
    """
    if not _AVAILABLE:
        return [], 0.0, False

    q = np.ascontiguousarray(query_coords, dtype=np.float32)
    r = np.ascontiguousarray(reference_coords, dtype=np.float32)

    q_angles = pke_cpp.compute_angles_from_coords(q)  # (T_q, 10)
    r_angles = pke_cpp.compute_angles_from_coords(r)  # (T_r, 10)
    path, cost = pke_cpp.compute_dtw(q_angles, r_angles, band_width)

    if not path:
        return [], float(cost), True

    # Per-joint mean absolute angular error along the warping path.
    errors = np.zeros(q_angles.shape[1], dtype=np.float32)
    for (i, j) in path:
        errors += np.abs(q_angles[i] - r_angles[j])
    errors /= len(path)

    # Normalize to 0-1 (max per-frame angular error is ~π radians).
    norm_errors = np.clip(errors / np.pi, 0.0, 1.0)

    joint_errors = [
        {
            "joint_index": idx,
            "joint_name": name,
            "error_score": float(norm_errors[idx]),
            "description": f"Avg angular deviation {np.degrees(float(errors[idx])):.1f}°",
        }
        for idx, name in enumerate(JOINT_NAMES[: q_angles.shape[1]])
    ]
    return joint_errors, float(cost), True
