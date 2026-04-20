"""
Unified PKE Model — combines ST-GCN backbone + Siamese projection head.

This is the single model object that the rest of the application interacts
with. It handles:
    - Forward pass (skeleton tensor → embedding)
    - Checkpoint loading/saving
    - Backbone freezing for calibration fine-tuning
    - Device management
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch
import torch.nn as nn
import numpy as np

from app.ml.stgcn import STGCN
from app.ml.siamese import SiameseHead

logger = logging.getLogger(__name__)


class PKEModel(nn.Module):
    """
    Full PKE model: ST-GCN backbone → Siamese projection head → embedding.

    Usage:
        model = PKEModel.from_checkpoint("checkpoints/pke_v1.pt")
        embedding = model.embed(normalized_tensor)  # (1, 256)
    """

    def __init__(
        self,
        in_channels: int = 3,
        block_channels: list[int] | None = None,
        hidden_dim: int = 512,
        embedding_dim: int = 256,
        temporal_kernel: int = 9,
        dropout: float = 0.1,
    ):
        super().__init__()

        self.backbone = STGCN(
            in_channels=in_channels,
            block_channels=block_channels,
            temporal_kernel=temporal_kernel,
            dropout=dropout,
        )
        self.head = SiameseHead(
            feature_dim=self.backbone.feature_dim,
            hidden_dim=hidden_dim,
            embedding_dim=embedding_dim,
            dropout=dropout,
        )

        self.embedding_dim = embedding_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Full forward pass: skeleton tensor → L2-normalized embedding.

        Args:
            x: (B, 3, T, 33) — normalized skeleton tensor from normalization.py.

        Returns:
            (B, embedding_dim) — L2-normalized embedding.
        """
        features = self.backbone(x)   # (B, feature_dim)
        embedding = self.head(features)  # (B, embedding_dim)
        return embedding

    @torch.no_grad()
    def embed(self, x: torch.Tensor | np.ndarray) -> np.ndarray:
        """
        Convenience method for inference: numpy in → numpy out.

        Handles torch/numpy conversion and ensures eval mode.

        Args:
            x: (1, 3, T, 33) or (B, 3, T, 33) — normalized skeleton tensor.

        Returns:
            (B, embedding_dim) numpy array of L2-normalized embeddings.
        """
        was_training = self.training
        self.eval()

        if isinstance(x, np.ndarray):
            x = torch.from_numpy(x).float()

        # Move to model's device
        device = next(self.parameters()).device
        x = x.to(device)

        embedding = self.forward(x)

        if was_training:
            self.train()

        return embedding.cpu().numpy()

    def freeze_backbone(self) -> None:
        """Freeze backbone weights for few-shot calibration fine-tuning."""
        for param in self.backbone.parameters():
            param.requires_grad = False
        logger.info("Backbone frozen — only projection head will be trained.")

    def unfreeze_backbone(self) -> None:
        """Unfreeze backbone weights for full pre-training."""
        for param in self.backbone.parameters():
            param.requires_grad = True
        logger.info("Backbone unfrozen — all parameters will be trained.")

    def save_checkpoint(self, path: str) -> None:
        """Save model weights to a checkpoint file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.state_dict(), path)
        logger.info(f"Checkpoint saved to {path}")

    @classmethod
    def from_checkpoint(
        cls,
        path: str,
        device: str = "cpu",
        **kwargs,
    ) -> "PKEModel":
        """
        Load a model from a checkpoint file.

        Args:
            path: Path to the .pt checkpoint file.
            device: Device to load the model onto.
            **kwargs: Additional arguments passed to the constructor
                      (block_channels, embedding_dim, etc.)

        Returns:
            Loaded PKEModel in eval mode.
        """
        model = cls(**kwargs)
        state_dict = torch.load(path, map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model.to(device)
        model.eval()
        logger.info(f"Model loaded from {path} on {device}")
        return model

    @classmethod
    def create_fresh(cls, device: str = "cpu", **kwargs) -> "PKEModel":
        """
        Create a fresh model with random weights (for pre-training).

        Args:
            device: Device to place the model on.
            **kwargs: Constructor arguments.

        Returns:
            Fresh PKEModel in train mode.
        """
        model = cls(**kwargs)
        model.to(device)
        model.train()
        param_count = sum(p.numel() for p in model.parameters())
        logger.info(
            f"Fresh model created on {device} — "
            f"{param_count:,} parameters ({param_count/1e6:.2f}M)"
        )
        return model
