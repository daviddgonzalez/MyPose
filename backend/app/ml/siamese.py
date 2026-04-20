"""
Siamese Projection Head.

Maps the ST-GCN backbone's feature vector into a normalized embedding space
suitable for metric learning (cosine distance comparison).

Architecture:
    Linear(feature_dim → hidden_dim) → BN → ReLU → Dropout
    Linear(hidden_dim → embedding_dim) → L2 Normalize

The projection head is the ONLY layer fine-tuned during user calibration.
The backbone remains frozen after pre-training.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class SiameseHead(nn.Module):
    """
    Projects backbone features into a compact, L2-normalized embedding space.

    This is intentionally shallow (2 layers) so that few-shot fine-tuning
    with 3-5 calibration sequences can adapt it meaningfully without
    overfitting.
    """

    def __init__(
        self,
        feature_dim: int = 256,
        hidden_dim: int = 512,
        embedding_dim: int = 256,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.projection = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, embedding_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, feature_dim) — backbone output features.

        Returns:
            (B, embedding_dim) — L2-normalized embeddings.
        """
        x = self.projection(x)
        # L2 normalize so cosine distance = 1 - dot product
        x = F.normalize(x, p=2, dim=1)
        return x


class ContrastiveLoss(nn.Module):
    """
    Contrastive loss for Siamese training.

    For positive pairs (same exercise, good form): minimize distance.
    For negative pairs (different exercise or bad form): push apart up to margin.

    L = (1-y) * 0.5 * D^2 + y * 0.5 * max(0, margin - D)^2

    where D = ||e1 - e2||_2, y=0 for positive, y=1 for negative.
    """

    def __init__(self, margin: float = 1.0):
        super().__init__()
        self.margin = margin

    def forward(
        self,
        embedding1: torch.Tensor,
        embedding2: torch.Tensor,
        label: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            embedding1: (B, D) — first embeddings (L2-normalized).
            embedding2: (B, D) — second embeddings (L2-normalized).
            label: (B,) — 0 for positive pair (same), 1 for negative pair (different).

        Returns:
            Scalar loss.
        """
        distance = F.pairwise_distance(embedding1, embedding2)
        positive_loss = (1 - label) * 0.5 * distance.pow(2)
        negative_loss = label * 0.5 * F.relu(self.margin - distance).pow(2)
        return (positive_loss + negative_loss).mean()
