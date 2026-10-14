"""
BVH parser + forward kinematics for the CMU Mocap pretraining path.

BVH stores a joint hierarchy with per-joint offsets and per-frame Euler
rotations — not world-space positions. To feed the ST-GCN we need 3D joint
trajectories, so this module composes each joint's local transform from the
motion channels and walks the hierarchy to produce world positions.

The cgspeed Motionbuilder-friendly conversion (the source for
una-dinosauria/cmu-mocap) inserts a T-pose adjustment in the very first
frame. `parse_bvh` exposes `drop_first_frame=True` by default so that
artifact never reaches training data.

Units / axes: cgspeed BVH is Y-up, centimeters, 120 fps. We don't rescale
here (the downstream normalize_landmarks step rescales by torso length
anyway); we just expose `fps` so the dataset can stride-downsample.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from bvh import Bvh


@dataclass
class BVHData:
    """Parsed BVH ready for forward kinematics."""
    joint_names: list[str]      # hierarchy DFS order; len == num_joints
    positions: np.ndarray       # (T, num_joints, 3), world-space, after FK
    fps: float                  # frames per second (1 / frame_time)


def parse_bvh(path: str | Path, drop_first_frame: bool = True) -> BVHData:
    """
    Parse a BVH file and run forward kinematics.

    Args:
        path: Path to a `.bvh` file.
        drop_first_frame: If True, drop frame 0 (the cgspeed T-pose artifact).

    Returns:
        BVHData with joint world positions of shape (T, num_joints, 3).
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    mocap = Bvh(content)

    joint_names = mocap.get_joints_names()
    positions = _forward_kinematics(mocap, joint_names)

    if drop_first_frame and positions.shape[0] > 1:
        positions = positions[1:]

    fps = 1.0 / float(mocap.frame_time) if mocap.frame_time else 120.0
    return BVHData(joint_names=joint_names, positions=positions, fps=fps)


def _forward_kinematics(mocap: Bvh, joint_names: list[str]) -> np.ndarray:
    """
    Compose per-joint local transforms from motion channels and chain them
    through the hierarchy to produce world-space positions.

    Vectorized across frames: each joint's per-frame rotation/translation
    is built as a (T, 3, 3) / (T, 3) batch, then world transforms are
    accumulated by (T, 4, 4) batched matmul.
    """
    num_joints = len(joint_names)

    motion = np.array(mocap.frames, dtype=np.float32)
    if motion.size == 0:
        return np.zeros((0, num_joints, 3), dtype=np.float32)
    T = motion.shape[0]

    parent_idx = _parent_indices(mocap, joint_names)

    local = np.zeros((T, num_joints, 4, 4), dtype=np.float32)
    local[:, :, 3, 3] = 1.0
    for j, name in enumerate(joint_names):
        offset = np.array(mocap.joint_offset(name), dtype=np.float32)
        channels = mocap.joint_channels(name)
        start = mocap.get_joint_channels_index(name)

        rot = np.broadcast_to(np.eye(3, dtype=np.float32), (T, 3, 3)).copy()
        translation = np.broadcast_to(offset, (T, 3)).copy()

        for k, ch in enumerate(channels):
            vals = motion[:, start + k]
            if ch == "Xposition":
                translation[:, 0] = translation[:, 0] + vals
            elif ch == "Yposition":
                translation[:, 1] = translation[:, 1] + vals
            elif ch == "Zposition":
                translation[:, 2] = translation[:, 2] + vals
            elif ch == "Xrotation":
                rot = rot @ _rot_x_batch(np.deg2rad(vals))
            elif ch == "Yrotation":
                rot = rot @ _rot_y_batch(np.deg2rad(vals))
            elif ch == "Zrotation":
                rot = rot @ _rot_z_batch(np.deg2rad(vals))

        local[:, j, :3, :3] = rot
        local[:, j, :3, 3] = translation

    world = np.zeros_like(local)
    for j in range(num_joints):
        if parent_idx[j] < 0:
            world[:, j] = local[:, j]
        else:
            world[:, j] = world[:, parent_idx[j]] @ local[:, j]

    return world[:, :, :3, 3].astype(np.float32)


def _parent_indices(mocap: Bvh, joint_names: list[str]) -> list[int]:
    name_to_idx = {n: i for i, n in enumerate(joint_names)}
    parents = [-1] * len(joint_names)
    for i, name in enumerate(joint_names):
        if i == 0:
            continue
        parent_node = mocap.joint_parent(name)
        if parent_node is None:
            continue
        parent_name = parent_node.value[1]
        parents[i] = name_to_idx.get(parent_name, -1)
    return parents


def _rot_x_batch(theta: np.ndarray) -> np.ndarray:
    """Batched 3×3 rotation about X-axis. `theta` shape (T,) in radians."""
    T = theta.shape[0]
    c, s = np.cos(theta), np.sin(theta)
    R = np.zeros((T, 3, 3), dtype=np.float32)
    R[:, 0, 0] = 1.0
    R[:, 1, 1] = c
    R[:, 1, 2] = -s
    R[:, 2, 1] = s
    R[:, 2, 2] = c
    return R


def _rot_y_batch(theta: np.ndarray) -> np.ndarray:
    T = theta.shape[0]
    c, s = np.cos(theta), np.sin(theta)
    R = np.zeros((T, 3, 3), dtype=np.float32)
    R[:, 0, 0] = c
    R[:, 0, 2] = s
    R[:, 1, 1] = 1.0
    R[:, 2, 0] = -s
    R[:, 2, 2] = c
    return R


def _rot_z_batch(theta: np.ndarray) -> np.ndarray:
    T = theta.shape[0]
    c, s = np.cos(theta), np.sin(theta)
    R = np.zeros((T, 3, 3), dtype=np.float32)
    R[:, 0, 0] = c
    R[:, 0, 1] = -s
    R[:, 1, 0] = s
    R[:, 1, 1] = c
    R[:, 2, 2] = 1.0
    return R
