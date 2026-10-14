"""
CMU Mocap (cgspeed BVH) → MediaPipe 33-joint retargeting.

The encoder is locked to MediaPipe Pose's 33-joint topology, so the CMU
skeleton must be projected into that layout. We pick the cgspeed joint
whose anatomical position best matches each MediaPipe joint; MediaPipe
joints with no CMU analog (face details, fingers, heels) are zero-filled
with visibility=0 — the same approach the NTU loader uses.

Mapping rationale:
  - MP shoulders/elbows/wrists come from cgspeed LeftArm/LeftForeArm/LeftHand
    (LeftShoulder in cgspeed is the clavicle root, not the shoulder joint).
  - MP hips come from LeftUpLeg/RightUpLeg (top of each leg in cgspeed).
  - MP foot_index comes from ToeBase.
  - MP nose (index 0) is approximated by cgspeed Head — close enough for
    a midline-head proxy under the existing centering/scaling pipeline.
"""

from __future__ import annotations

import numpy as np

NUM_MEDIAPIPE_JOINTS = 33


# cgspeed BVH joint name → MediaPipe Pose joint index.
# Names cover the standard cgspeed skeleton plus a few common variants.
_CMU_TO_MEDIAPIPE: dict[str, int] = {
    "Head": 0,           # nose (midline-head proxy)
    "LeftArm": 11,       # left shoulder
    "RightArm": 12,      # right shoulder
    "LeftForeArm": 13,   # left elbow
    "RightForeArm": 14,  # right elbow
    "LeftHand": 15,      # left wrist
    "RightHand": 16,     # right wrist
    "LeftFingerBase": 19,   # left index (closest hand-tip analog)
    "RightFingerBase": 20,  # right index
    "LeftUpLeg": 23,     # left hip
    "RightUpLeg": 24,    # right hip
    "LeftLeg": 25,       # left knee
    "RightLeg": 26,      # right knee
    "LeftFoot": 27,      # left ankle
    "RightFoot": 28,     # right ankle
    "LeftToeBase": 31,   # left foot index
    "RightToeBase": 32,  # right foot index
}


def retarget(
    cmu_positions: np.ndarray,
    joint_names: list[str],
) -> np.ndarray:
    """
    Project CMU joint trajectories onto a MediaPipe-33 layout.

    Args:
        cmu_positions: (T, N_cmu, 3) world-space positions from BVH FK.
        joint_names:   length-N_cmu list of joint names matching the second
                       axis of `cmu_positions`.

    Returns:
        (T, 33, 4) array where the last channel is visibility (1.0 for joints
        we filled, 0.0 for unmapped MediaPipe joints).
    """
    if cmu_positions.ndim != 3 or cmu_positions.shape[2] != 3:
        raise ValueError(f"Expected (T, N, 3) input, got {cmu_positions.shape}")
    if cmu_positions.shape[1] != len(joint_names):
        raise ValueError(
            f"joint_names length {len(joint_names)} does not match positions axis 1 {cmu_positions.shape[1]}"
        )

    T = cmu_positions.shape[0]
    out = np.zeros((T, NUM_MEDIAPIPE_JOINTS, 4), dtype=np.float32)

    name_to_idx = {n: i for i, n in enumerate(joint_names)}
    for cmu_name, mp_idx in _CMU_TO_MEDIAPIPE.items():
        cmu_idx = name_to_idx.get(cmu_name)
        if cmu_idx is None:
            continue
        out[:, mp_idx, :3] = cmu_positions[:, cmu_idx, :]
        out[:, mp_idx, 3] = 1.0

    return out
