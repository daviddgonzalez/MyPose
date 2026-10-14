"""
Training Scripts — Pre-Training and Calibration Fine-Tuning.

Two entry points:
    1. pretrain()  — Train backbone + head on Fit3D contrastive pairs.
                     Run offline, produces a checkpoint for deployment.
    2. finetune()  — Fine-tune ONLY the projection head on a user's
                     3-5 calibration sequences. Runs in-process during
                     calibration finalization (~seconds).

Usage (pre-training):
    python -m app.ml.training pretrain --data-dir data/fit3d --epochs 50

Usage (fine-tuning — called programmatically):
    from app.ml.training import finetune
    finetune(model, user_sequences, lr=1e-4, epochs=10)
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from app.config import settings
from app.ml.model import PKEModel
from app.ml.siamese import ContrastiveLoss, NTXentLoss
from app.ml.dataset import Fit3DContrastiveDataset
from app.services.normalization import normalize_landmarks

logger = logging.getLogger(__name__)


def _build_dataset(
    dataset_name: str,
    data_dir: str,
    sequence_length: int,
) -> torch.utils.data.Dataset:
    """
    Build a contrastive view-pair dataset by name.

    Supported:
      - "fit3d": Fit3DContrastiveDataset over Fit3D raw/preprocessed data.
      - "ntu":   NTUContrastiveDataset over NTU RGB+D 120 .skeleton files.
      - "cmu":   CMUContrastiveDataset over cgspeed BVH conversion of CMU Mocap.
      - "both":  ConcatDataset of Fit3D + NTU.
    """
    name = dataset_name.lower()
    if name == "fit3d":
        return Fit3DContrastiveDataset(data_dir=data_dir, sequence_length=sequence_length)
    if name == "ntu":
        from app.ml.dataset_ntu import NTUContrastiveDataset
        return NTUContrastiveDataset(data_dir=data_dir, sequence_length=sequence_length)
    if name == "cmu":
        from app.ml.dataset_cmu import CMUContrastiveDataset
        return CMUContrastiveDataset(data_dir=data_dir, sequence_length=sequence_length)
    if name == "both":
        from app.ml.dataset_ntu import NTUContrastiveDataset
        fit = Fit3DContrastiveDataset(data_dir=data_dir, sequence_length=sequence_length)
        ntu = NTUContrastiveDataset(data_dir=data_dir, sequence_length=sequence_length)
        return torch.utils.data.ConcatDataset([fit, ntu])
    raise ValueError(f"Unknown dataset: {dataset_name!r}. Use one of: fit3d, ntu, cmu, both")


def pretrain(
    data_dir: str,
    checkpoint_dir: str = "checkpoints",
    epochs: int = 50,
    batch_size: int = 16,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    temperature: float = 0.1,
    device: str = "cpu",
    sequence_length: int = 64,
    embedding_dim: int = 256,
    log_interval: int = 10,
    dataset_name: str = "fit3d",
    resume_from: str | None = None,
    checkpoint_suffix: str = "",
) -> str:
    """
    Pre-train the full model (backbone + head) using NT-Xent contrastive loss.

    Each dataset sample yields two augmented views of the same sequence; in-batch
    negatives provide the contrastive signal. See app/ml/augment.py for the
    augmentation policy and app/ml/siamese.py:NTXentLoss for the loss.

    Args:
        data_dir: Root data directory (contains fit3d/, ntu/, etc.) or, for
                  --dataset cmu, the CMU dataset root (e.g., ~/datasets/cmu-mocap).
        checkpoint_dir: Directory to save checkpoints.
        epochs: Number of training epochs.
        batch_size: Training batch size (NT-Xent benefits from larger batches).
        lr: Learning rate.
        weight_decay: L2 regularization.
        temperature: NT-Xent temperature τ. Smaller = sharper contrast; tune in [0.05, 0.2].
        device: "cpu" or "cuda".
        sequence_length: Temporal length for normalization.
        embedding_dim: Embedding dimension.
        log_interval: Log every N batches.
        dataset_name: "fit3d", "ntu", "cmu", or "both".
        resume_from: Path to a checkpoint to warm-start from (e.g., NTU pretrain
                     to seed a Fit3D fine-pretrain). None = train from scratch.
        checkpoint_suffix: Appended to checkpoint filenames so two-stage runs
                           don't clobber each other (e.g., "_ntu", "_fit3d").

    Returns:
        Path to the best checkpoint produced by this run.
    """
    logger.info("=" * 60)
    logger.info(f"Starting pre-training on {dataset_name!r}")
    logger.info(f"  Data: {data_dir}")
    logger.info(f"  Epochs: {epochs}, Batch: {batch_size}, LR: {lr}, τ: {temperature}")
    logger.info(f"  Device: {device}, Resume: {resume_from or 'no'}")
    logger.info("=" * 60)

    dataset = _build_dataset(dataset_name, data_dir, sequence_length)
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,  # Keep 0 for Windows compatibility
        drop_last=True,
    )

    if resume_from:
        model = PKEModel.from_checkpoint(resume_from, device=device)
        model.unfreeze_backbone()
        logger.info(f"Warm-started from {resume_from}")
    else:
        model = PKEModel.create_fresh(device=device, embedding_dim=embedding_dim)
        model.unfreeze_backbone()

    criterion = NTXentLoss(temperature=temperature)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=lr,
        weight_decay=weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_loss = float("inf")
    best_name = f"pke_pretrained{checkpoint_suffix}.pt"
    final_name = f"pke_pretrained_final{checkpoint_suffix}.pt"
    checkpoint_path = str(Path(checkpoint_dir) / best_name)

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        num_batches = 0
        start_time = time.time()

        for batch_idx, batch in enumerate(dataloader):
            view1, view2 = batch
            view1 = view1.to(device)
            view2 = view2.to(device)

            emb1 = model(view1)
            emb2 = model(view2)

            loss = criterion(emb1, emb2)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

            if (batch_idx + 1) % log_interval == 0:
                logger.info(
                    f"  Epoch {epoch}/{epochs} | Batch {batch_idx+1}/{len(dataloader)} | "
                    f"Loss: {loss.item():.4f}"
                )

        scheduler.step()
        avg_loss = epoch_loss / max(num_batches, 1)
        elapsed = time.time() - start_time

        logger.info(
            f"Epoch {epoch}/{epochs} complete — "
            f"Avg Loss: {avg_loss:.4f} | "
            f"LR: {scheduler.get_last_lr()[0]:.6f} | "
            f"Time: {elapsed:.1f}s"
        )

        if avg_loss < best_loss:
            best_loss = avg_loss
            model.save_checkpoint(checkpoint_path)
            logger.info(f"  ✓ New best loss — checkpoint saved ({best_name})")

    final_path = str(Path(checkpoint_dir) / final_name)
    model.save_checkpoint(final_path)

    logger.info("=" * 60)
    logger.info(f"Pre-training complete. Best loss: {best_loss:.4f}")
    logger.info(f"Best checkpoint: {checkpoint_path}")
    logger.info(f"Final checkpoint: {final_path}")
    logger.info("=" * 60)

    return checkpoint_path


def _load_negatives_bank(path: Path, device: str) -> torch.Tensor | None:
    """
    Load the precomputed negatives bank if present. Returns a (N, D) tensor on
    `device`, or None if the file is missing.
    """
    if not path.exists():
        logger.info(f"No negatives bank at {path}; finetune will use positives only")
        return None
    bank = np.load(path).astype(np.float32)
    if bank.ndim != 2:
        logger.warning(f"Negatives bank at {path} has unexpected shape {bank.shape}; ignoring")
        return None
    logger.info(f"Loaded negatives bank: shape {bank.shape}")
    return torch.from_numpy(bank).to(device)


def finetune(
    model: PKEModel,
    sequences: list[np.ndarray],
    lr: float = 1e-4,
    epochs: int = 10,
    margin: float = 0.5,
    sequence_length: int = 64,
    negatives_bank_path: str | Path | None = None,
    negatives_per_anchor: int = 3,
) -> PKEModel:
    """
    Fine-tune the projection head on a user's calibration sequences.

    The backbone is frozen; only the projection head trains. Positive pairs
    come from all (i, j) combinations of calibration sequences. If a negatives
    bank is available, each calibration embedding is also paired against K
    random fixed bank vectors as negatives — this gives the head a "push apart"
    signal it otherwise lacks.

    Args:
        model: Pre-trained PKEModel (will be modified in-place).
        sequences: List of raw landmark arrays, each (T, 33, 4).
        lr: Fine-tuning learning rate.
        epochs: Number of fine-tuning epochs.
        margin: Contrastive loss margin.
        sequence_length: Temporal length for normalization.
        negatives_bank_path: Path to checkpoints/negatives_bank.npy. Defaults
            to `<checkpoint_dir>/negatives_bank.npy` from settings.
        negatives_per_anchor: K negatives per calibration sequence per epoch.

    Returns:
        Fine-tuned model (same object, modified in-place).
    """
    if len(sequences) < 2:
        logger.warning("Need at least 2 sequences for contrastive fine-tuning")
        return model

    logger.info(f"Fine-tuning projection head on {len(sequences)} sequences")

    model.freeze_backbone()
    model.train()

    device = next(model.parameters()).device

    cal_tensors = []
    for seq in sequences:
        if seq.shape[-1] == 3:
            vis = np.ones((*seq.shape[:-1], 1), dtype=np.float32)
            seq = np.concatenate([seq, vis], axis=-1)
        normalized = normalize_landmarks(seq, sequence_length)
        cal_tensors.append(torch.from_numpy(normalized[0]).to(device))

    cal_batch = torch.stack(cal_tensors, dim=0)  # (M, 3, T, 33)
    m = cal_batch.shape[0]

    # Indices for all (i, j) positive pairs.
    pos_i: list[int] = []
    pos_j: list[int] = []
    for i in range(m):
        for j in range(i + 1, m):
            pos_i.append(i)
            pos_j.append(j)
    if not pos_i:
        logger.warning("No calibration pairs generated for fine-tuning")
        model.eval()
        return model

    pos_i_t = torch.tensor(pos_i, device=device, dtype=torch.long)
    pos_j_t = torch.tensor(pos_j, device=device, dtype=torch.long)

    # Resolve negatives bank path: explicit > settings default. None = no negatives.
    if negatives_bank_path is None:
        bank_path = Path(settings.checkpoint_dir) / "negatives_bank.npy"
    else:
        bank_path = Path(negatives_bank_path)
    bank = _load_negatives_bank(bank_path, device)

    optimizer = torch.optim.Adam(model.head.parameters(), lr=lr)
    criterion = ContrastiveLoss(margin=margin)

    for epoch in range(1, epochs + 1):
        emb_cal = model(cal_batch)  # (M, D)

        # Positive term: matching calibration embeddings, label=0.
        emb_a = emb_cal[pos_i_t]
        emb_b = emb_cal[pos_j_t]
        labels = torch.zeros((emb_a.shape[0],), device=device)

        if bank is not None and bank.shape[0] > 0:
            k = min(negatives_per_anchor, bank.shape[0])
            neg_idx = torch.randint(0, bank.shape[0], (m, k), device=device)
            neg_vecs = bank[neg_idx.flatten()]            # (M*K, D)
            anchor_repeated = emb_cal.repeat_interleave(k, dim=0)  # (M*K, D)
            neg_labels = torch.ones((anchor_repeated.shape[0],), device=device)
            emb_a = torch.cat([emb_a, anchor_repeated], dim=0)
            emb_b = torch.cat([emb_b, neg_vecs], dim=0)
            labels = torch.cat([labels, neg_labels], dim=0)

        loss = criterion(emb_a, emb_b, labels)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        avg_loss = float(loss.item())
        if epoch % 3 == 0 or epoch == 1:
            logger.info(f"  Fine-tune epoch {epoch}/{epochs} — Loss: {avg_loss:.6f}")

    model.eval()
    logger.info("Fine-tuning complete")
    return model


def compute_centroid_and_threshold(
    model: PKEModel,
    sequences: list[np.ndarray],
    sequence_length: int = 64,
    margin: float = 0.05,
) -> tuple[np.ndarray, float]:
    """
    Compute the centroid (mean embedding) and a data-driven threshold from
    the user's calibration sequences.

    The threshold is set to the maximum intra-cluster distance + a small
    margin, so a future session that is "no farther from the centroid than
    your own calibration reps" passes the Personal match check. This makes
    the threshold reflect the user's actual movement variance rather than a
    one-size-fits-all constant.

    Args:
        model: Fine-tuned PKEModel.
        sequences: List of raw landmark arrays, each (T, 33, 4).
        sequence_length: Temporal length for normalization.
        margin: Buffer added to max intra-cluster distance.

    Returns:
        (centroid, threshold). centroid is shape (embedding_dim,).
    """
    embeddings = []
    for seq in sequences:
        if seq.shape[-1] == 3:
            vis = np.ones((*seq.shape[:-1], 1), dtype=np.float32)
            seq = np.concatenate([seq, vis], axis=-1)
        normalized = normalize_landmarks(seq, sequence_length)
        emb = model.embed(normalized)  # (1, embedding_dim)
        embeddings.append(emb[0])

    centroid = np.mean(embeddings, axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)

    distances = [float(1.0 - np.dot(e, centroid)) for e in embeddings]
    intra_max = max(distances) if distances else 0.0
    threshold = intra_max + margin

    logger.info(
        f"Centroid: {len(embeddings)} embeddings, "
        f"intra-cluster mean={np.mean(distances):.4f} max={intra_max:.4f} -> "
        f"threshold={threshold:.4f}"
    )
    return centroid, threshold


def compute_centroid(
    model: PKEModel,
    sequences: list[np.ndarray],
    sequence_length: int = 64,
) -> np.ndarray:
    """Backwards-compatible wrapper. Prefer compute_centroid_and_threshold."""
    centroid, _ = compute_centroid_and_threshold(model, sequences, sequence_length)
    return centroid


# ─── CLI Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(description="PKE Model Training")
    subparsers = parser.add_subparsers(dest="command")

    # Pre-train command
    pt = subparsers.add_parser("pretrain", help="NT-Xent pretrain on skeleton data")
    pt.add_argument("--data-dir", required=True, help="Root data directory")
    pt.add_argument("--checkpoint-dir", default="checkpoints")
    pt.add_argument("--epochs", type=int, default=50)
    pt.add_argument("--batch-size", type=int, default=16)
    pt.add_argument("--lr", type=float, default=1e-3)
    pt.add_argument("--temperature", type=float, default=0.1)
    pt.add_argument("--device", default="cpu")
    pt.add_argument("--embedding-dim", type=int, default=256)
    pt.add_argument(
        "--dataset",
        choices=["fit3d", "ntu", "cmu", "both"],
        default="fit3d",
        help="Which dataset to pretrain on",
    )
    pt.add_argument("--resume-from", default=None, help="Checkpoint to warm-start from")
    pt.add_argument(
        "--checkpoint-suffix",
        default="",
        help="Suffix on saved checkpoint filename (e.g., _ntu, _fit3d)",
    )

    args = parser.parse_args()

    if args.command == "pretrain":
        pretrain(
            data_dir=args.data_dir,
            checkpoint_dir=args.checkpoint_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            temperature=args.temperature,
            device=args.device,
            embedding_dim=args.embedding_dim,
            dataset_name=args.dataset,
            resume_from=args.resume_from,
            checkpoint_suffix=args.checkpoint_suffix,
        )
    else:
        parser.print_help()
