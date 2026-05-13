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
    Pair-based contrastive loss. Retained for the calibration finetune path
    (see training.finetune); pretraining now uses NTXentLoss.

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
        distance = F.pairwise_distance(embedding1, embedding2)
        positive_loss = (1 - label) * 0.5 * distance.pow(2)
        negative_loss = label * 0.5 * F.relu(self.margin - distance).pow(2)
        return (positive_loss + negative_loss).mean()


class NTXentLoss(nn.Module):
    """
    Normalized temperature-scaled cross-entropy loss (SimCLR-style).

    Given a batch of N samples each producing two augmented views, build the
    2N x 2N cosine similarity matrix, mask the diagonal, and treat the matching
    view as the only positive class for each row. All other 2N-2 entries are
    negatives in the softmax denominator.

    Embeddings must already be L2-normalized (SiameseHead does this).
    """

    def __init__(self, temperature: float = 0.1):
        super().__init__()
        self.temperature = temperature

    def forward(self, view1: torch.Tensor, view2: torch.Tensor) -> torch.Tensor:
        """
        Args:
            view1, view2: (N, D) — L2-normalized embeddings of two augmented views.

        Returns:
            Scalar NT-Xent loss averaged over 2N anchors.
        """
        batch_size = view1.shape[0]
        device = view1.device

        # Stack to (2N, D)
        embeddings = torch.cat([view1, view2], dim=0)

        # Cosine similarity matrix (2N, 2N) — inputs are L2-normalized so
        # dot product == cosine similarity.
        sim = embeddings @ embeddings.T
        sim = sim / self.temperature

        # Mask out self-similarity on the diagonal.
        diag_mask = torch.eye(2 * batch_size, dtype=torch.bool, device=device)
        sim = sim.masked_fill(diag_mask, float("-inf"))

        # For row i in the first half, positive is i + batch_size.
        # For row i in the second half, positive is i - batch_size.
        positive_indices = torch.arange(2 * batch_size, device=device)
        positive_indices = (positive_indices + batch_size) % (2 * batch_size)

        return F.cross_entropy(sim, positive_indices)
