"""
Fit3D Dataset Loader for ST-GCN Pre-Training.

Loads skeleton sequences from the Fit3D dataset and produces self-supervised
contrastive views for NT-Xent training. Each `__getitem__` call returns two
*independently augmented* versions of the same sequence; the contrastive
signal comes from in-batch negatives at the loss layer (see siamese.NTXentLoss).

Expected directory layout after pre-processing:
    data/fit3d/
    ├── squat/
    │   ├── sequence_001.npy    # shape: (T, 33, 3)
    │   ├── sequence_002.npy
    │   └── ...
    ├── deadlift/
    │   └── ...
    └── ...

Each .npy file should contain a single exercise repetition or short clip,
already mapped to MediaPipe's 33-joint topology.
"""

from __future__ import annotations

import logging
import random
import json
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import Dataset

from app.ml.augment import augment_skeleton
from app.services.normalization import normalize_landmarks

logger = logging.getLogger(__name__)

# Exercises that exist in both Fit3D and our catalog
SUPPORTED_EXERCISES = [
    "squat",
    "deadlift",
    "lunge",
    "push_up",
    "plank",
    "overhead_press",
    "barbell_biceps_curl",
]

# Raw Fit3D filename aliases -> canonical exercise names used by the app.
EXERCISE_ALIASES = {
    "squat": "squat",
    "deadlift": "deadlift",
    "dumbbell_reverse_lunge": "lunge",
    "pushup": "push_up",
    "diamond_pushup": "push_up",
    "dumbbell_overhead_shoulder_press": "overhead_press",
    "neutral_overhead_shoulder_press": "overhead_press",
    "dumbbell_biceps_curls": "barbell_biceps_curl",
    "dumbbell_hammer_curls": "barbell_biceps_curl",
    "drag_curl": "barbell_biceps_curl",
}


class Fit3DContrastiveDataset(Dataset):
    """
    Self-supervised contrastive dataset for NT-Xent pretraining.

    Each `__getitem__` returns TWO independently-augmented views of the same
    underlying sequence. The contrastive signal comes from in-batch negatives
    in NTXentLoss: views from the same anchor are positives, all other batch
    elements are negatives.

    Pre-augmentation comes from `app.ml.augment.augment_skeleton`. Augmentations
    run on raw (T, 33, C) landmarks BEFORE the centering/scaling/resampling
    pipeline in normalize_landmarks so temporal crops and rotations ride the
    existing math.
    """

    def __init__(
        self,
        data_dir: str,
        sequence_length: int = 64,
        max_sequences_per_exercise: Optional[int] = None,
        augment: bool = True,
    ):
        """
        Args:
            data_dir: Path to the fit3d/ directory containing exercise subfolders.
            sequence_length: Target temporal length for normalization.
            max_sequences_per_exercise: Cap per exercise (for dev/debugging).
            augment: When False, both views are identical (no augmentations).
                     Used by Fit3DSingleDataset for embedding extraction.
        """
        self.data_dir = Path(data_dir)
        self.sequence_length = sequence_length
        self.augment = augment

        # Index all sequences by exercise
        self.exercise_sequences: dict[str, list[Path]] = {}
        self.all_sequences: list[tuple[str, Path]] = []

        # Support both:
        # 1) Preprocessed layout: fit3d/<exercise>/*.npy
        # 2) Raw Fit3D layout: fit3d_train/train/sXX/joints3d_25/*.json (+ optional test)
        self._index_preprocessed_layout(max_sequences_per_exercise)
        if not self.all_sequences:
            self._index_raw_fit3d_layout(max_sequences_per_exercise)

        self.exercises = list(self.exercise_sequences.keys())
        total = len(self.all_sequences)
        logger.info(
            f"Fit3D dataset loaded: {total} sequences across "
            f"{len(self.exercises)} exercises"
        )

        if total == 0:
            raise ValueError(
                f"No sequences found in {data_dir}. "
                f"Expected subdirectories: {SUPPORTED_EXERCISES}"
            )

    def _index_preprocessed_layout(self, max_sequences_per_exercise: Optional[int]) -> None:
        for exercise in SUPPORTED_EXERCISES:
            exercise_dir = self.data_dir / exercise
            if not exercise_dir.exists():
                continue

            npy_files = sorted(exercise_dir.glob("*.npy"))
            if max_sequences_per_exercise:
                npy_files = npy_files[:max_sequences_per_exercise]

            if npy_files:
                self.exercise_sequences[exercise] = npy_files
                for f in npy_files:
                    self.all_sequences.append((exercise, f))
                logger.info(f"  {exercise}: {len(npy_files)} sequences (.npy)")

    def _index_raw_fit3d_layout(self, max_sequences_per_exercise: Optional[int]) -> None:
        # Accept both when data_dir points at backend/data or a nested fit3d_{train,test} folder.
        candidate_roots = [
            self.data_dir / "fit3d_train" / "train",
            self.data_dir / "fit3d_test" / "test",
            self.data_dir / "train",
            self.data_dir / "test",
        ]

        for root in candidate_roots:
            if not root.exists():
                continue
            for subject_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
                joints_dir = subject_dir / "joints3d_25"
                if not joints_dir.exists():
                    continue

                for json_path in sorted(joints_dir.glob("*.json")):
                    raw_name = json_path.stem
                    canonical = EXERCISE_ALIASES.get(raw_name)
                    if canonical is None:
                        continue
                    self.exercise_sequences.setdefault(canonical, []).append(json_path)

        for exercise, files in self.exercise_sequences.items():
            selected = files[:max_sequences_per_exercise] if max_sequences_per_exercise else files
            self.exercise_sequences[exercise] = selected
            for f in selected:
                self.all_sequences.append((exercise, f))
            logger.info(f"  {exercise}: {len(selected)} sequences (raw Fit3D json)")

    def __len__(self) -> int:
        # Each sequence can be paired, so dataset size = number of anchor sequences
        return len(self.all_sequences)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            (view1, view2) where each view is a (3, T, 33) normalized tensor
            obtained by augmenting the same source sequence independently.
        """
        _, path = self.all_sequences[idx]
        raw = self._load_raw(path)  # (T, 33, 4)
        view1 = self._augment_and_normalize(raw)
        view2 = self._augment_and_normalize(raw)
        return view1, view2

    def _load_raw(self, path: Path) -> np.ndarray:
        """Load a sequence file and return raw (T, 33, 4) landmarks with visibility."""
        if path.suffix.lower() == ".npy":
            landmarks = np.load(path).astype(np.float32)
        elif path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if "joints3d_25" not in payload:
                raise ValueError(f"Expected 'joints3d_25' in {path}")
            joints25 = np.array(payload["joints3d_25"], dtype=np.float32)
            if joints25.ndim != 3 or joints25.shape[1] != 25 or joints25.shape[2] != 3:
                raise ValueError(f"Unexpected joints3d_25 shape in {path}: {joints25.shape}")
            landmarks = np.zeros((joints25.shape[0], 33, 3), dtype=np.float32)
            landmarks[:, :25, :] = joints25
        else:
            raise ValueError(f"Unsupported sequence format: {path.suffix}")

        if landmarks.shape[-1] == 3:
            visibility = np.ones((*landmarks.shape[:-1], 1), dtype=np.float32)
            landmarks = np.concatenate([landmarks, visibility], axis=-1)
        return landmarks

    def _augment_and_normalize(self, landmarks: np.ndarray) -> torch.Tensor:
        """Augment (if enabled) then run through the normalization pipeline."""
        if self.augment:
            landmarks = augment_skeleton(landmarks)
        normalized = normalize_landmarks(landmarks, self.sequence_length)
        return torch.from_numpy(normalized[0])

    def load_normalized(self, idx: int) -> torch.Tensor:
        """Non-augmented load of one sequence — used for embedding extraction."""
        _, path = self.all_sequences[idx]
        raw = self._load_raw(path)
        normalized = normalize_landmarks(raw, self.sequence_length)
        return torch.from_numpy(normalized[0])


class Fit3DSingleDataset(Dataset):
    """
    Single-sequence dataset (non-contrastive) for embedding extraction.

    Returns individual normalized sequences with their exercise labels.
    Used for validation, visualization, and centroid computation.
    """

    def __init__(
        self,
        data_dir: str,
        sequence_length: int = 64,
        max_sequences_per_exercise: Optional[int] = None,
    ):
        self.data_dir = Path(data_dir)
        self.sequence_length = sequence_length

        self.sequences: list[tuple[str, Path]] = []
        self.exercise_to_idx: dict[str, int] = {}

        # Keep this utility dataset aligned with the same mixed-format indexing.
        for i, exercise in enumerate(SUPPORTED_EXERCISES):
            self.exercise_to_idx[exercise] = i

        contrastive = Fit3DContrastiveDataset(
            data_dir=data_dir,
            sequence_length=sequence_length,
            max_sequences_per_exercise=max_sequences_per_exercise,
        )
        for exercise, path in contrastive.all_sequences:
            self.sequences.append((exercise, path))

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int, str]:
        """
        Returns:
            (tensor, exercise_idx, exercise_name) where:
                tensor: (3, T, 33) normalized tensor
                exercise_idx: integer label
                exercise_name: string label
        """
        exercise, path = self.sequences[idx]
        if path.suffix.lower() == ".npy":
            landmarks = np.load(path).astype(np.float32)
        elif path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            joints25 = np.array(payload["joints3d_25"], dtype=np.float32)
            landmarks = np.zeros((joints25.shape[0], 33, 3), dtype=np.float32)
            landmarks[:, :25, :] = joints25
        else:
            raise ValueError(f"Unsupported sequence format: {path.suffix}")

        if landmarks.shape[-1] == 3:
            visibility = np.ones((*landmarks.shape[:-1], 1), dtype=np.float32)
            landmarks = np.concatenate([landmarks, visibility], axis=-1)

        normalized = normalize_landmarks(landmarks, self.sequence_length)
        tensor = torch.from_numpy(normalized[0])

        return tensor, self.exercise_to_idx[exercise], exercise
