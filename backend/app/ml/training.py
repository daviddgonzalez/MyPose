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

from app.ml.model import PKEModel
from app.ml.siamese import ContrastiveLoss
from app.ml.dataset import Fit3DContrastiveDataset
from app.services.normalization import normalize_landmarks

logger = logging.getLogger(__name__)


def pretrain(
    data_dir: str,
    checkpoint_dir: str = "checkpoints",
    epochs: int = 50,
    batch_size: int = 16,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    margin: float = 1.0,
    device: str = "cpu",
    sequence_length: int = 64,
    embedding_dim: int = 256,
    log_interval: int = 10,
) -> str:
    """
    Pre-train the full model (backbone + head) on the Fit3D dataset.

    Uses contrastive learning: same-exercise pairs should produce similar
    embeddings, different-exercise pairs should be pushed apart.

    Args:
        data_dir: Path to the Fit3D data directory.
        checkpoint_dir: Directory to save checkpoints.
        epochs: Number of training epochs.
        batch_size: Training batch size.
        lr: Learning rate.
        weight_decay: L2 regularization.
        margin: Contrastive loss margin.
        device: "cpu" or "cuda".
        sequence_length: Temporal length for normalization.
        embedding_dim: Embedding dimension.
        log_interval: Log every N batches.

    Returns:
        Path to the saved checkpoint.
    """
    logger.info("=" * 60)
    logger.info("Starting Fit3D pre-training")
    logger.info(f"  Data: {data_dir}")
    logger.info(f"  Epochs: {epochs}, Batch: {batch_size}, LR: {lr}")
    logger.info(f"  Device: {device}")
    logger.info("=" * 60)

    # Dataset
    dataset = Fit3DContrastiveDataset(
        data_dir=data_dir,
        sequence_length=sequence_length,
    )
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,  # Keep 0 for Windows compatibility
        drop_last=True,
    )

    # Model
    model = PKEModel.create_fresh(
        device=device,
        embedding_dim=embedding_dim,
    )
    model.unfreeze_backbone()

    # Loss & Optimizer
    criterion = ContrastiveLoss(margin=margin)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=lr,
        weight_decay=weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Training loop
    best_loss = float("inf")
    checkpoint_path = ""

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        num_batches = 0
        start_time = time.time()

        for batch_idx, (anchor, pair, label) in enumerate(dataloader):
            anchor = anchor.to(device)
            pair = pair.to(device)
            label = label.to(device)

            # Forward pass
            emb_anchor = model(anchor)
            emb_pair = model(pair)

            # Contrastive loss
            loss = criterion(emb_anchor, emb_pair, label)

            # Backward pass
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

        # Save best checkpoint
        if avg_loss < best_loss:
            best_loss = avg_loss
            checkpoint_path = str(Path(checkpoint_dir) / "pke_pretrained.pt")
            model.save_checkpoint(checkpoint_path)
            logger.info(f"  ✓ New best loss — checkpoint saved")

    # Save final checkpoint
    final_path = str(Path(checkpoint_dir) / "pke_pretrained_final.pt")
    model.save_checkpoint(final_path)

    logger.info("=" * 60)
    logger.info(f"Pre-training complete. Best loss: {best_loss:.4f}")
    logger.info(f"Best checkpoint: {checkpoint_path}")
    logger.info(f"Final checkpoint: {final_path}")
    logger.info("=" * 60)

    return checkpoint_path


def finetune(
    model: PKEModel,
    sequences: list[np.ndarray],
    lr: float = 1e-4,
    epochs: int = 10,
    margin: float = 0.5,
    sequence_length: int = 64,
) -> PKEModel:
    """
    Fine-tune the projection head on a user's calibration sequences.

    Called during calibration finalization. The backbone is frozen and only
    the projection head is updated to adapt the embedding space to this
    user's specific movement patterns.

    Args:
        model: Pre-trained PKEModel (will be modified in-place).
        sequences: List of raw landmark arrays, each (T, 33, 4).
        lr: Fine-tuning learning rate (lower than pre-training).
        epochs: Number of fine-tuning epochs.
        margin: Contrastive loss margin (tighter than pre-training).
        sequence_length: Temporal length for normalization.

    Returns:
        Fine-tuned model (same object, modified in-place).
    """
    if len(sequences) < 2:
        logger.warning("Need at least 2 sequences for contrastive fine-tuning")
        return model

    logger.info(f"Fine-tuning projection head on {len(sequences)} sequences")

    # Freeze backbone, only train head
    model.freeze_backbone()
    model.train()

    device = next(model.parameters()).device

    # Normalize all sequences → tensors
    tensors = []
    for seq in sequences:
        # seq shape: (T, 33, 4) or (T, 33, 3)
        if seq.shape[-1] == 3:
            vis = np.ones((*seq.shape[:-1], 1), dtype=np.float32)
            seq = np.concatenate([seq, vis], axis=-1)
        normalized = normalize_landmarks(seq, sequence_length)  # (1, 3, T, 33)
        tensors.append(torch.from_numpy(normalized[0]).to(device))  # (3, T, 33)

    # Optimizer for head only
    optimizer = torch.optim.Adam(model.head.parameters(), lr=lr)
    criterion = ContrastiveLoss(margin=margin)

    # Build all positive pairs once; train with a batched forward pass so
    # BatchNorm in the head can update running stats during calibration.
    anchor_batch = []
    pair_batch = []
    for i in range(len(tensors)):
        for j in range(i + 1, len(tensors)):
            anchor_batch.append(tensors[i])
            pair_batch.append(tensors[j])

    if not anchor_batch:
        logger.warning("No calibration pairs generated for fine-tuning")
        model.eval()
        return model

    anchors = torch.stack(anchor_batch, dim=0)  # (P, 3, T, 33)
    pairs = torch.stack(pair_batch, dim=0)      # (P, 3, T, 33)
    labels = torch.zeros((anchors.shape[0],), device=device)  # all positive

    for epoch in range(1, epochs + 1):
        emb_a = model(anchors)
        emb_b = model(pairs)
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


def compute_centroid(
    model: PKEModel,
    sequences: list[np.ndarray],
    sequence_length: int = 64,
) -> np.ndarray:
    """
    Compute the centroid (mean embedding) from calibration sequences.

    Args:
        model: Fine-tuned PKEModel.
        sequences: List of raw landmark arrays, each (T, 33, 4).
        sequence_length: Temporal length for normalization.

    Returns:
        Centroid vector of shape (embedding_dim,).
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
    # Re-normalize the centroid
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)

    logger.info(
        f"Centroid computed from {len(embeddings)} embeddings — "
        f"norm: {np.linalg.norm(centroid):.4f}"
    )
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
    pt = subparsers.add_parser("pretrain", help="Pre-train on Fit3D dataset")
    pt.add_argument("--data-dir", required=True, help="Path to Fit3D data directory")
    pt.add_argument("--checkpoint-dir", default="checkpoints")
    pt.add_argument("--epochs", type=int, default=50)
    pt.add_argument("--batch-size", type=int, default=16)
    pt.add_argument("--lr", type=float, default=1e-3)
    pt.add_argument("--device", default="cpu")
    pt.add_argument("--embedding-dim", type=int, default=256)

    args = parser.parse_args()

    if args.command == "pretrain":
        pretrain(
            data_dir=args.data_dir,
            checkpoint_dir=args.checkpoint_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            device=args.device,
            embedding_dim=args.embedding_dim,
        )
    else:
        parser.print_help()
