"""
NTU RGB+D 120 Dataset Loader for ST-GCN Pre-Training.

Provides a contrastive view-pair dataset over the NTU RGB+D 120 skeleton corpus
(114k clips, 106 subjects, 120 action classes, 25-joint Kinect-v2 3D skeletons).
The subject diversity is the primary lever — Fit3D's ~13 subjects produce
embeddings that collapse onto subject style; NTU's ~106 force the backbone to
learn motion structure instead.

Dataset acquisition (one-time human work):
    1. Register at https://rose1.ntu.edu.sg/dataset/actionRecognition/ (ROSE Lab).
    2. Download "NTU RGB+D 120" skeleton subset (the .skeleton text files).
    3. Unpack into backend/data/ntu/nturgbd_skeletons/ — flat directory of
       SxxxCxxxPxxxRxxxAxxx.skeleton files.
    4. Optionally also drop samples_with_missing_skeletons.txt from the official
       repo at backend/data/ntu/ — those filenames will be skipped on indexing.

Skeleton file format (per the public NTU spec):
    line: numFrames
    for each frame:
        line: numBodies
        for each body:
            line: bodyID + 9 tracking fields (we ignore)
            line: numJoints (always 25)
            25 lines: x y z depthX depthY colorX colorY orientW orientX orientY orientZ trackingState
We keep only the FIRST body's (x, y, z) per frame.

NTU 25-joint (Kinect v2) → MediaPipe 33-joint mapping:
    See _NTU_TO_MEDIAPIPE below. Joints not present in NTU (face details, heels)
    are left zero with visibility=0; the normalization pipeline uses hip+shoulder
    midpoints which are well covered.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import Dataset

from app.ml.augment import augment_skeleton
from app.services.normalization import normalize_landmarks

logger = logging.getLogger(__name__)


# NTU joint index → MediaPipe Pose joint index.
# Comments give the NTU semantic name (Kinect v2 convention).
_NTU_TO_MEDIAPIPE: dict[int, int] = {
    3: 0,    # head        → nose (best available midline-head proxy)
    4: 11,   # L shoulder  → L shoulder
    8: 12,   # R shoulder  → R shoulder
    5: 13,   # L elbow     → L elbow
    9: 14,   # R elbow     → R elbow
    6: 15,   # L wrist     → L wrist
    10: 16,  # R wrist     → R wrist
    7: 19,   # L hand      → L index (closest hand-tip analog)
    11: 20,  # R hand      → R index
    12: 23,  # L hip       → L hip
    16: 24,  # R hip       → R hip
    13: 25,  # L knee      → L knee
    17: 26,  # R knee      → R knee
    14: 27,  # L ankle     → L ankle
    18: 28,  # R ankle     → R ankle
    15: 31,  # L foot      → L foot index
    19: 32,  # R foot      → R foot index
}


def _ntu_to_mediapipe_layout(joints25: np.ndarray) -> np.ndarray:
    """
    Project (T, 25, 3) NTU joints into a (T, 33, 4) MediaPipe-shaped tensor.
    Mapped joints get visibility=1; unmapped joints stay zero with visibility=0.
    """
    t = joints25.shape[0]
    out = np.zeros((t, 33, 4), dtype=np.float32)
    for ntu_idx, mp_idx in _NTU_TO_MEDIAPIPE.items():
        out[:, mp_idx, :3] = joints25[:, ntu_idx, :]
        out[:, mp_idx, 3] = 1.0
    return out


def _parse_ntu_skeleton(path: Path) -> np.ndarray:
    """
    Parse an NTU .skeleton file and return (T, 25, 3) joint positions from the
    first tracked body. Returns an empty array if no bodies are present.
    """
    with path.open("r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    idx = 0
    num_frames = int(lines[idx]); idx += 1
    frames: list[np.ndarray] = []

    for _ in range(num_frames):
        if idx >= len(lines):
            break
        num_bodies = int(lines[idx]); idx += 1
        first_body_joints: Optional[np.ndarray] = None

        for body_i in range(num_bodies):
            # Body header (1 line — bodyID + tracking fields), skip.
            idx += 1
            num_joints = int(lines[idx]); idx += 1
            joints = np.zeros((num_joints, 3), dtype=np.float32)
            for j in range(num_joints):
                parts = lines[idx].split()
                joints[j, 0] = float(parts[0])
                joints[j, 1] = float(parts[1])
                joints[j, 2] = float(parts[2])
                idx += 1
            if body_i == 0:
                first_body_joints = joints

        if first_body_joints is not None:
            frames.append(first_body_joints)

    if not frames:
        return np.zeros((0, 25, 3), dtype=np.float32)
    return np.stack(frames, axis=0)


class NTUContrastiveDataset(Dataset):
    """
    Self-supervised contrastive dataset over NTU RGB+D 120 skeletons.

    Identical view-pair contract as Fit3DContrastiveDataset: each __getitem__
    returns two independently augmented views of the same clip.
    """

    SKELETON_SUBDIRS = ("ntu/nturgbd_skeletons", "ntu", "nturgbd_skeletons")
    MISSING_MANIFEST = "ntu/samples_with_missing_skeletons.txt"

    def __init__(
        self,
        data_dir: str,
        sequence_length: int = 64,
        max_files: Optional[int] = None,
        min_frames: int = 8,
        augment: bool = True,
    ):
        """
        Args:
            data_dir: Root data directory; NTU files are expected under one of
                      SKELETON_SUBDIRS.
            sequence_length: Target temporal length for normalization.
            max_files: Cap total clip count (for dev/debugging).
            min_frames: Skip clips with fewer than this many frames after parse.
            augment: When False, both views are identical (used for embedding
                     extraction utilities).
        """
        self.data_dir = Path(data_dir)
        self.sequence_length = sequence_length
        self.min_frames = min_frames
        self.augment = augment

        missing = self._load_missing_manifest()
        skeleton_root = self._find_skeleton_root()
        if skeleton_root is None:
            raise FileNotFoundError(
                f"No NTU skeleton directory found under {self.data_dir}. "
                f"Tried: {self.SKELETON_SUBDIRS}"
            )

        self.files: list[Path] = []
        for path in sorted(skeleton_root.glob("*.skeleton")):
            if path.stem in missing:
                continue
            self.files.append(path)
            if max_files is not None and len(self.files) >= max_files:
                break

        logger.info(f"NTU dataset loaded: {len(self.files)} skeleton files from {skeleton_root}")
        if not self.files:
            raise ValueError(f"No .skeleton files found in {skeleton_root}")

    def _find_skeleton_root(self) -> Optional[Path]:
        for sub in self.SKELETON_SUBDIRS:
            candidate = self.data_dir / sub
            if candidate.exists() and any(candidate.glob("*.skeleton")):
                return candidate
        return None

    def _load_missing_manifest(self) -> set[str]:
        manifest = self.data_dir / self.MISSING_MANIFEST
        if not manifest.exists():
            return set()
        with manifest.open("r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip() and not line.startswith("#")}

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        path = self.files[idx]
        raw = self._load_raw(path)
        if raw.shape[0] < self.min_frames:
            # Fall back to a different sample to avoid degenerate clips poisoning
            # a batch. Rotate index deterministically; if everything is short,
            # the dataset itself is broken and we let it surface upstream.
            return self.__getitem__((idx + 1) % len(self.files))
        view1 = self._augment_and_normalize(raw)
        view2 = self._augment_and_normalize(raw)
        return view1, view2

    def _load_raw(self, path: Path) -> np.ndarray:
        joints25 = _parse_ntu_skeleton(path)
        if joints25.shape[0] == 0:
            return np.zeros((0, 33, 4), dtype=np.float32)
        return _ntu_to_mediapipe_layout(joints25)

    def _augment_and_normalize(self, landmarks: np.ndarray) -> torch.Tensor:
        if self.augment:
            landmarks = augment_skeleton(landmarks)
        normalized = normalize_landmarks(landmarks, self.sequence_length)
        return torch.from_numpy(normalized[0])
