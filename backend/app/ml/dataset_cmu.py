"""
CMU Mocap Dataset Loader for ST-GCN Pre-Training.

Provides a contrastive view-pair dataset over the cgspeed BVH conversion of
the CMU Graphics Lab Motion Capture Database (~2,548 motions, ~144 subjects).
Subject diversity is the lever: Fit3D's ~13 subjects collapse embeddings
onto subject style; CMU's ~144 force the backbone to learn motion structure.

Dataset acquisition (one-time):
    python -m scripts.download_cmu_mocap [--dest <path>]
    (defaults to ~/datasets/cmu-mocap)

Per-sample pipeline:
    1. Parse BVH + forward kinematics → (T, N_cmu, 3) world positions.
    2. Retarget cgspeed joints onto MediaPipe 33-joint layout → (T, 33, 4).
    3. Stride-downsample 120 fps → settings.target_fps (default 30).
    4. Random window of ~2 × sequence_length frames (gives the temporal-crop
       augmentation room to maneuver without exploding memory on long clips).
    5. Two independent augmentations + normalizations → (view1, view2).

CMU motions have no class labels; the pretraining loss (NT-Xent in
backend/app/ml/siamese.py) uses augmentation-based positives so this is fine.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import Dataset

from app.config import settings
from app.ml.augment import augment_skeleton
from app.ml.bvh_loader import parse_bvh
from app.ml.cmu_to_mediapipe import retarget
from app.services.normalization import normalize_landmarks

logger = logging.getLogger(__name__)

CGSPEED_FPS = 120


class CMUContrastiveDataset(Dataset):
    """Self-supervised contrastive dataset over CMU Mocap BVH files."""

    def __init__(
        self,
        data_dir: str,
        sequence_length: int = 64,
        window_frames: Optional[int] = None,
        min_frames: int = 16,
        max_files: Optional[int] = None,
        augment: bool = True,
        target_fps: Optional[int] = None,
    ):
        """
        Args:
            data_dir: Root directory containing .bvh files (recursive scan).
            sequence_length: Target temporal length for normalization.
            window_frames: Length of the random window sampled per __getitem__
                           (after fps downsampling). Defaults to 2 × sequence_length.
            min_frames: Skip clips shorter than this (after fps downsampling).
            max_files: Optional cap on indexed files (dev/debug only).
            augment: When False, both views are identical (for embedding utils).
            target_fps: Downsample target. Defaults to settings.target_fps.
        """
        self.data_dir = Path(data_dir).expanduser()
        self.sequence_length = sequence_length
        self.window_frames = window_frames if window_frames is not None else 2 * sequence_length
        self.min_frames = min_frames
        self.augment = augment
        self.target_fps = target_fps if target_fps is not None else settings.target_fps

        if CGSPEED_FPS % self.target_fps != 0:
            raise ValueError(
                f"target_fps {self.target_fps} must divide CGSPEED_FPS {CGSPEED_FPS} evenly"
            )
        self.stride = CGSPEED_FPS // self.target_fps

        if not self.data_dir.exists():
            raise FileNotFoundError(
                f"CMU data directory not found: {self.data_dir}. "
                f"Run: python -m scripts.download_cmu_mocap --dest {self.data_dir}"
            )

        self.files: list[Path] = sorted(self.data_dir.rglob("*.bvh"))
        if max_files is not None:
            self.files = self.files[:max_files]
        if not self.files:
            raise ValueError(f"No .bvh files found under {self.data_dir}")

        logger.info(
            "CMU dataset loaded: %d BVH files from %s (stride=%d, window=%d frames)",
            len(self.files), self.data_dir, self.stride, self.window_frames,
        )

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        path = self.files[idx]
        try:
            landmarks = self._load_clip(path)
        except Exception as e:
            logger.warning("Failed to load %s (%s); falling back to next index", path.name, e)
            return self.__getitem__((idx + 1) % len(self.files))

        if landmarks.shape[0] < self.min_frames:
            return self.__getitem__((idx + 1) % len(self.files))

        windowed = self._random_window(landmarks)
        view1 = self._augment_and_normalize(windowed)
        view2 = self._augment_and_normalize(windowed)
        return view1, view2

    def _load_clip(self, path: Path) -> np.ndarray:
        """Parse + FK + retarget + downsample → (T_down, 33, 4)."""
        bvh = parse_bvh(path, drop_first_frame=True)
        positions = bvh.positions
        if positions.shape[0] == 0:
            return np.zeros((0, 33, 4), dtype=np.float32)

        # cgspeed BVH is 120 fps; target_fps divides it evenly.
        if self.stride > 1:
            positions = positions[:: self.stride]

        return retarget(positions, bvh.joint_names)

    def _random_window(self, landmarks: np.ndarray) -> np.ndarray:
        T = landmarks.shape[0]
        if T <= self.window_frames:
            return landmarks
        start = random.randint(0, T - self.window_frames)
        return landmarks[start : start + self.window_frames]

    def _augment_and_normalize(self, landmarks: np.ndarray) -> torch.Tensor:
        if self.augment:
            landmarks = augment_skeleton(landmarks)
        normalized = normalize_landmarks(landmarks, self.sequence_length)
        return torch.from_numpy(normalized[0])
