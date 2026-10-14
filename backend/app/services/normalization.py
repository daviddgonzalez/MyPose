"""
Landmark Normalization Service.

Transforms raw MediaPipe landmarks into model-ready tensors via three steps:
  1. Root-relative centering (hip midpoint at origin per frame)
  2. Scale invariance (normalize by torso length per frame)
  3. Temporal resampling (fixed-length sequence via linear interpolation)

Input:  (T, 33, 4)  — raw landmarks from extraction (x, y, z, visibility)
Output: (1, 3, T_fixed, 33) — model-ready tensor (Batch, Channels, Time, Joints)
"""

from __future__ import annotations

import numpy as np

from app.config import settings

# MediaPipe Pose landmark indices (key anatomical points)
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12


def normalize_landmarks(
    landmarks: np.ndarray,
    sequence_length: int | None = None,
) -> np.ndarray:
    """
    Full normalization pipeline: center → scale → resample → reshape.

    Args:
        landmarks: Raw landmarks of shape (T, 33, 4) from extraction.
        sequence_length: Target temporal length. Defaults to settings.sequence_length (64).

    Returns:
        Normalized tensor of shape (1, 3, sequence_length, 33) ready for ST-GCN.
    """
    if sequence_length is None:
        sequence_length = settings.sequence_length

    # Strip visibility → (T, 33, 3) — we only need x, y, z for the model
    coords = landmarks[:, :, :3].copy()

    # Step 1: Root-relative centering
    coords = _root_center(coords)

    # Step 2: Scale invariance
    coords = _scale_normalize(coords)

    # Step 3: Temporal resampling to fixed length
    coords = _resample_temporal(coords, sequence_length)

    # Step 4: Reshape for ST-GCN input convention
    # From (T, 33, 3) → (1, 3, T, 33)
    # Transpose: (T, J, C) → (C, T, J) then add batch dim
    tensor = coords.transpose(2, 0, 1)  # (3, T, 33)
    tensor = np.expand_dims(tensor, axis=0)  # (1, 3, T, 33)

    return tensor.astype(np.float32)


def _root_center(coords: np.ndarray) -> np.ndarray:
    """
    Translate all joints so the hip midpoint is at origin per frame.

    The root point is the average of left hip (23) and right hip (24),
    which is the most stable anatomical reference point.

    Args:
        coords: Shape (T, 33, 3).

    Returns:
        Root-centered coords of same shape.
    """
    # Hip midpoint per frame: (T, 3)
    hip_mid = (coords[:, LEFT_HIP, :] + coords[:, RIGHT_HIP, :]) / 2.0

    # Broadcast subtract: (T, 33, 3) - (T, 1, 3)
    centered = coords - hip_mid[:, np.newaxis, :]

    return centered


def _scale_normalize(coords: np.ndarray) -> np.ndarray:
    """
    Scale all joints by torso length per frame for size invariance.

    Torso length = distance from hip midpoint to shoulder midpoint.
    This removes body-size differences between users.

    Args:
        coords: Root-centered coords of shape (T, 33, 3).

    Returns:
        Scale-normalized coords of same shape.
    """
    # Hip midpoint: already at origin after centering, but recompute for clarity
    hip_mid = (coords[:, LEFT_HIP, :] + coords[:, RIGHT_HIP, :]) / 2.0

    # Shoulder midpoint per frame: (T, 3)
    shoulder_mid = (coords[:, LEFT_SHOULDER, :] + coords[:, RIGHT_SHOULDER, :]) / 2.0

    # Torso length per frame: (T,)
    torso_length = np.linalg.norm(shoulder_mid - hip_mid, axis=1)

    # Avoid division by zero (e.g., if pose detection failed on a frame)
    torso_length = np.maximum(torso_length, 1e-6)

    # Broadcast divide: (T, 33, 3) / (T, 1, 1)
    normalized = coords / torso_length[:, np.newaxis, np.newaxis]

    return normalized


def _resample_temporal(coords: np.ndarray, target_length: int) -> np.ndarray:
    """
    Resample the sequence to a fixed number of frames via linear interpolation.

    This ensures all sequences have identical temporal dimension regardless
    of the original video length or recording FPS.

    Args:
        coords: Shape (T_original, 33, 3).
        target_length: Desired number of frames (e.g., 64).

    Returns:
        Resampled coords of shape (target_length, 33, 3).
    """
    t_original = coords.shape[0]

    if t_original == target_length:
        return coords

    # Source and target time indices
    source_indices = np.linspace(0, t_original - 1, t_original)
    target_indices = np.linspace(0, t_original - 1, target_length)

    # Interpolate each joint coordinate independently
    # coords shape: (T, 33, 3) → flatten last two dims for vectorized interp
    t, j, c = coords.shape
    flat = coords.reshape(t, j * c)  # (T, 99)

    resampled_flat = np.zeros((target_length, j * c), dtype=coords.dtype)
    for col in range(j * c):
        resampled_flat[:, col] = np.interp(target_indices, source_indices, flat[:, col])

    return resampled_flat.reshape(target_length, j, c)  # (target_length, 33, 3)


def compute_joint_angles(coords: np.ndarray) -> np.ndarray:
    """
    Compute angles at each joint from 3D coordinates.

    Used by the DTW fallback to compare joint-level kinematics.
    For each joint with two neighboring bones, computes the angle
    between the bone vectors using the dot product formula.

    Args:
        coords: Shape (T, 33, 3) — normalized or raw coordinates.

    Returns:
        Joint angles of shape (T, N_angles) where N_angles depends on
        the skeleton topology.
    """
    # Define joint triplets: (parent, joint, child) → angle at 'joint'
    # Based on MediaPipe Pose connections for major body joints
    angle_triplets = [
        # Right arm
        (RIGHT_SHOULDER, 14, 16),  # shoulder → elbow → wrist
        (RIGHT_HIP, RIGHT_SHOULDER, 14),  # hip → shoulder → elbow
        # Left arm
        (LEFT_SHOULDER, 13, 15),   # shoulder → elbow → wrist
        (LEFT_HIP, LEFT_SHOULDER, 13),   # hip → shoulder → elbow
        # Right leg
        (RIGHT_HIP, 26, 28),      # hip → knee → ankle
        (0, RIGHT_HIP, 26),       # nose/root → hip → knee (trunk angle)
        # Left leg
        (LEFT_HIP, 25, 27),       # hip → knee → ankle
        (0, LEFT_HIP, 25),        # nose/root → hip → knee
        # Torso
        (LEFT_HIP, RIGHT_HIP, RIGHT_SHOULDER),  # hip alignment
        (LEFT_SHOULDER, RIGHT_SHOULDER, RIGHT_HIP),  # shoulder alignment
    ]

    t_frames = coords.shape[0]
    angles = np.zeros((t_frames, len(angle_triplets)), dtype=np.float32)

    for i, (p, j, c) in enumerate(angle_triplets):
        # Bone vectors
        vec_a = coords[:, p, :] - coords[:, j, :]  # parent → joint
        vec_b = coords[:, c, :] - coords[:, j, :]  # child → joint

        # Dot product and magnitudes
        dot = np.sum(vec_a * vec_b, axis=1)
        mag_a = np.linalg.norm(vec_a, axis=1)
        mag_b = np.linalg.norm(vec_b, axis=1)

        # Cosine of angle (clamp to [-1, 1] for numerical stability)
        cos_angle = np.clip(dot / (mag_a * mag_b + 1e-8), -1.0, 1.0)
        angles[:, i] = np.arccos(cos_angle)  # Radians

    return angles
