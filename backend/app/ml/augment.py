"""
Skeleton augmentations for contrastive pretraining.

Operates on raw (pre-normalization) landmark arrays of shape (T, 33, C) where
C is 3 (x,y,z) or 4 (x,y,z,visibility). MediaPipe Pose 33-joint topology is
assumed; the left/right mirror table is defined for this topology.

Apply this BEFORE normalize_landmarks so the temporal-crop and rotation
augmentations can ride the existing centering/scaling/resampling pipeline.

Augmentations applied (each independently, with their own probability):
  - temporal_crop_resize: random crop 60-100% of frames; downstream resampling
    re-stretches to fixed length. Forces invariance to where in the rep we
    start/end.
  - rotate_y: ±max_deg rotation about the vertical (camera-facing) axis.
    Forces invariance to user orientation.
  - mirror_flip: swap left/right joints + negate x. Doubles effective subjects.
  - joint_mask: zero out a random subset of joint indices for the whole clip.
    Strongest single augmentation per AimCLR ablations.
  - gaussian_jitter: small additive noise on coordinates.
"""

from __future__ import annotations

import numpy as np

# MediaPipe Pose 33-joint topology: indices that swap under a left/right mirror.
# Joints not in this list (nose=0, midline) stay fixed.
_MEDIAPIPE_LR_PAIRS: tuple[tuple[int, int], ...] = (
    (1, 4),    # eye inner
    (2, 5),    # eye
    (3, 6),    # eye outer
    (7, 8),    # ear
    (9, 10),   # mouth corner
    (11, 12),  # shoulder
    (13, 14),  # elbow
    (15, 16),  # wrist
    (17, 18),  # pinky
    (19, 20),  # index
    (21, 22),  # thumb
    (23, 24),  # hip
    (25, 26),  # knee
    (27, 28),  # ankle
    (29, 30),  # heel
    (31, 32),  # foot index
)


def augment_skeleton(
    landmarks: np.ndarray,
    *,
    p_temporal: float = 0.8,
    p_rotate: float = 0.5,
    p_mirror: float = 0.5,
    p_joint_mask: float = 0.8,
    p_jitter: float = 0.8,
    crop_min: float = 0.6,
    rotate_max_deg: float = 30.0,
    joint_mask_max_frac: float = 0.2,
    jitter_sigma: float = 0.02,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Apply random augmentations to a single skeleton clip.

    Args:
        landmarks: (T, 33, 3) or (T, 33, 4) raw landmarks.
        rng: optional numpy Generator for reproducibility; defaults to per-call random state.

    Returns:
        Augmented landmarks, same shape and dtype as input.
    """
    if rng is None:
        rng = np.random.default_rng()

    out = landmarks.astype(np.float32, copy=True)

    if rng.random() < p_temporal:
        out = _temporal_crop(out, crop_min, rng)
    if rng.random() < p_rotate:
        out = _rotate_y(out, rotate_max_deg, rng)
    if rng.random() < p_mirror:
        out = _mirror_flip(out)
    if rng.random() < p_joint_mask:
        out = _joint_mask(out, joint_mask_max_frac, rng)
    if rng.random() < p_jitter:
        out = _gaussian_jitter(out, jitter_sigma, rng)

    return out


def _temporal_crop(landmarks: np.ndarray, crop_min: float, rng: np.random.Generator) -> np.ndarray:
    t = landmarks.shape[0]
    if t < 4:
        return landmarks
    frac = rng.uniform(crop_min, 1.0)
    new_len = max(2, int(round(t * frac)))
    start = rng.integers(0, t - new_len + 1)
    return landmarks[start : start + new_len]


def _rotate_y(landmarks: np.ndarray, max_deg: float, rng: np.random.Generator) -> np.ndarray:
    theta = np.deg2rad(rng.uniform(-max_deg, max_deg))
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    # Rotation about the vertical (Y) axis. xyz columns: [x, y, z]; Y stays put,
    # x and z mix. landmarks visibility channel (col 3 if present) is untouched.
    rot = np.array(
        [[cos_t, 0.0, sin_t],
         [0.0,   1.0, 0.0  ],
         [-sin_t, 0.0, cos_t]],
        dtype=np.float32,
    )
    out = landmarks.copy()
    xyz = out[..., :3]
    out[..., :3] = xyz @ rot.T
    return out


def _mirror_flip(landmarks: np.ndarray) -> np.ndarray:
    out = landmarks.copy()
    # Negate the lateral (x) axis.
    out[..., 0] = -out[..., 0]
    # Swap left/right joint indices.
    for left, right in _MEDIAPIPE_LR_PAIRS:
        if left < out.shape[1] and right < out.shape[1]:
            tmp = out[:, left, :].copy()
            out[:, left, :] = out[:, right, :]
            out[:, right, :] = tmp
    return out


def _joint_mask(landmarks: np.ndarray, max_frac: float, rng: np.random.Generator) -> np.ndarray:
    n_joints = landmarks.shape[1]
    n_mask = int(round(rng.uniform(0.05, max_frac) * n_joints))
    if n_mask <= 0:
        return landmarks
    indices = rng.choice(n_joints, size=n_mask, replace=False)
    out = landmarks.copy()
    out[:, indices, :3] = 0.0
    return out


def _gaussian_jitter(landmarks: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    out = landmarks.copy()
    noise = rng.normal(0.0, sigma, size=out[..., :3].shape).astype(np.float32)
    out[..., :3] = out[..., :3] + noise
    return out
