"""
Fit3D Dataset Loader for ST-GCN Pre-Training.

Loads skeleton sequences from the Fit3D dataset and prepares contrastive
pairs for Siamese training. Fit3D provides 3D body joint positions from
fitness exercises captured with multiple cameras.

Expected directory layout after pre-processing:
    data/fit3d/
    ├── squat/
    │   ├── sequence_001.npy    # shape: (T, 33, 3)
    │   ├── sequence_002.npy
    │   └── ...
    ├── deadlift/
    │   └── ...
    ├── lunge/
    │   └── ...
    └── ...

Each .npy file should contain a single exercise repetition or short clip,
already mapped to MediaPipe's 33-joint topology. The loader handles
normalization via the existing services/normalization.py pipeline.

Pre-processing script (separate): converts Fit3D's raw SMPL-X joints to
MediaPipe-compatible 33-joint format and saves as .npy files.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import Dataset

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


class Fit3DContrastiveDataset(Dataset):
    """
    Contrastive pair dataset for Siamese pre-training.

    Returns pairs of normalized skeleton sequences with labels:
        - label=0 (positive): both sequences are from the SAME exercise
        - label=1 (negative): sequences are from DIFFERENT exercises

    The ratio of positive to negative pairs is approximately 50/50.
    """

    def __init__(
        self,
        data_dir: str,
        sequence_length: int = 64,
        max_sequences_per_exercise: Optional[int] = None,
    ):
        """
        Args:
            data_dir: Path to the fit3d/ directory containing exercise subfolders.
            sequence_length: Target temporal length for normalization.
            max_sequences_per_exercise: Cap per exercise (for dev/debugging).
        """
        self.data_dir = Path(data_dir)
        self.sequence_length = sequence_length

        # Index all sequences by exercise
        self.exercise_sequences: dict[str, list[Path]] = {}
        self.all_sequences: list[tuple[str, Path]] = []

        for exercise in SUPPORTED_EXERCISES:
            exercise_dir = self.data_dir / exercise
            if not exercise_dir.exists():
                logger.warning(f"Exercise directory not found: {exercise_dir}")
                continue

            npy_files = sorted(exercise_dir.glob("*.npy"))
            if max_sequences_per_exercise:
                npy_files = npy_files[:max_sequences_per_exercise]

            if npy_files:
                self.exercise_sequences[exercise] = npy_files
                for f in npy_files:
                    self.all_sequences.append((exercise, f))
                logger.info(f"  {exercise}: {len(npy_files)} sequences")

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

    def __len__(self) -> int:
        # Each sequence can be paired, so dataset size = number of anchor sequences
        return len(self.all_sequences)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns:
            (anchor, pair, label) where:
                anchor: (3, T, 33) normalized tensor
                pair:   (3, T, 33) normalized tensor
                label:  scalar tensor, 0=positive, 1=negative
        """
        anchor_exercise, anchor_path = self.all_sequences[idx]

        # 50% chance positive pair (same exercise), 50% negative (different)
        if random.random() < 0.5 and len(self.exercise_sequences[anchor_exercise]) > 1:
            # Positive pair: different sequence, same exercise
            candidates = [
                p for p in self.exercise_sequences[anchor_exercise]
                if p != anchor_path
            ]
            pair_path = random.choice(candidates)
            label = 0.0
        else:
            # Negative pair: different exercise
            other_exercises = [e for e in self.exercises if e != anchor_exercise]
            if other_exercises:
                neg_exercise = random.choice(other_exercises)
                pair_path = random.choice(self.exercise_sequences[neg_exercise])
                label = 1.0
            else:
                # Fallback: only one exercise available, use same as positive
                pair_path = random.choice(self.exercise_sequences[anchor_exercise])
                label = 0.0

        anchor_tensor = self._load_and_normalize(anchor_path)
        pair_tensor = self._load_and_normalize(pair_path)

        return anchor_tensor, pair_tensor, torch.tensor(label, dtype=torch.float32)

    def _load_and_normalize(self, path: Path) -> torch.Tensor:
        """Load a .npy sequence and run through the normalization pipeline."""
        # Load raw landmarks: expected shape (T, 33, 3)
        landmarks = np.load(path).astype(np.float32)

        # Add visibility channel if missing → (T, 33, 4)
        if landmarks.shape[-1] == 3:
            visibility = np.ones((*landmarks.shape[:-1], 1), dtype=np.float32)
            landmarks = np.concatenate([landmarks, visibility], axis=-1)

        # Run through the existing normalization pipeline
        # Output shape: (1, 3, T, 33)
        normalized = normalize_landmarks(landmarks, self.sequence_length)

        # Remove batch dim → (3, T, 33) and convert to torch
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

        for i, exercise in enumerate(SUPPORTED_EXERCISES):
            exercise_dir = self.data_dir / exercise
            if not exercise_dir.exists():
                continue

            self.exercise_to_idx[exercise] = i
            npy_files = sorted(exercise_dir.glob("*.npy"))
            if max_sequences_per_exercise:
                npy_files = npy_files[:max_sequences_per_exercise]

            for f in npy_files:
                self.sequences.append((exercise, f))

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
        landmarks = np.load(path).astype(np.float32)

        if landmarks.shape[-1] == 3:
            visibility = np.ones((*landmarks.shape[:-1], 1), dtype=np.float32)
            landmarks = np.concatenate([landmarks, visibility], axis=-1)

        normalized = normalize_landmarks(landmarks, self.sequence_length)
        tensor = torch.from_numpy(normalized[0])

        return tensor, self.exercise_to_idx[exercise], exercise
