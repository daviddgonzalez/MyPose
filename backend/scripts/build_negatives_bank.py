"""
Build the negatives bank used by the calibration finetune.

Embeds a fixed set of non-squat Fit3D clips with the current pretrained backbone
and saves the resulting (N, embedding_dim) array to
`checkpoints/negatives_bank.npy`. The finetune step (training.finetune) loads
this bank and pairs each user calibration sequence with K random bank entries
as negative (label=1) pairs, giving the projection head an actual
"push these apart" signal it lacks today.

Re-run this script once per new pretrained checkpoint:

    python -m scripts.build_negatives_bank \
        --checkpoint checkpoints/pke_pretrained.pt \
        --data-dir data \
        --out checkpoints/negatives_bank.npy \
        --count 50 \
        --exclude squat

The CLI matches the pretrain CLI's conventions (run from `backend/`).
"""

from __future__ import annotations

import argparse
import logging
import random
from pathlib import Path

import numpy as np

from app.config import settings
from app.ml.dataset import Fit3DContrastiveDataset
from app.ml.model import PKEModel

logger = logging.getLogger(__name__)


def build_negatives_bank(
    checkpoint: str,
    data_dir: str,
    out_path: str,
    count: int = 50,
    exclude_exercise: str = "squat",
    sequence_length: int = 64,
    device: str = "cpu",
    seed: int = 0,
) -> str:
    """
    Embed `count` non-`exclude_exercise` clips and save them to `out_path`.

    Returns the absolute path of the saved file.
    """
    random.seed(seed)
    np.random.seed(seed)

    model = PKEModel.from_checkpoint(checkpoint, device=device)
    model.eval()

    dataset = Fit3DContrastiveDataset(
        data_dir=data_dir,
        sequence_length=sequence_length,
        augment=False,
    )

    candidates = [
        i for i, (exercise, _) in enumerate(dataset.all_sequences)
        if exercise != exclude_exercise
    ]
    if not candidates:
        raise RuntimeError(
            f"No non-{exclude_exercise} sequences found in {data_dir}. "
            f"Available exercises: {dataset.exercises}"
        )

    random.shuffle(candidates)
    chosen = candidates[:count]
    logger.info(
        f"Selecting {len(chosen)} non-{exclude_exercise} clips from {len(candidates)} candidates"
    )

    embeddings = np.zeros((len(chosen), settings.embedding_dim), dtype=np.float32)
    for row, idx in enumerate(chosen):
        tensor = dataset.load_normalized(idx).unsqueeze(0).numpy()  # (1, 3, T, 33)
        embedding = model.embed(tensor)[0]
        embeddings[row] = embedding

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, embeddings)
    logger.info(f"Negatives bank saved: {out} — shape {embeddings.shape}")
    return str(out.resolve())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build calibration-finetune negatives bank.")
    parser.add_argument("--checkpoint", required=True, help="Pretrained checkpoint path")
    parser.add_argument("--data-dir", required=True, help="Data root with fit3d data")
    parser.add_argument("--out", default="checkpoints/negatives_bank.npy")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--exclude", default="squat", help="Exercise to exclude from the bank")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = _parse_args()
    build_negatives_bank(
        checkpoint=args.checkpoint,
        data_dir=args.data_dir,
        out_path=args.out,
        count=args.count,
        exclude_exercise=args.exclude,
        device=args.device,
        seed=args.seed,
    )
