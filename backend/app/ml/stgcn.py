"""
Spatio-Temporal Graph Convolutional Network (ST-GCN) Backbone.

Processes sequences of 33-joint skeleton poses and outputs a fixed-length
feature vector capturing both spatial (joint-to-joint) and temporal (frame-
to-frame) movement patterns.

Architecture:
    3 × ST-GCN blocks  →  Global Average Pool  →  Feature vector
    Each block: Graph Conv (spatial) + Temporal Conv + BatchNorm + ReLU + Dropout

Input:  (B, 3, T, 33)  — batch, xyz channels, time frames, joints
Output: (B, feature_dim) — feature_dim = last block's channel count (256)

Reference: Yan et al., "Spatial Temporal Graph Convolutional Networks for
Skeleton-Based Action Recognition", AAAI 2018.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# ─── MediaPipe Pose Skeleton Topology ────────────────────────────
# Defines which joints are connected. Used to build the adjacency
# matrix for graph convolution.
#
# MediaPipe Pose has 33 landmarks. The edges below represent the
# anatomical bone connections.
_MEDIAPIPE_EDGES = [
    # Head / face
    (0, 1), (1, 2), (2, 3), (3, 7),     # nose → right ear
    (0, 4), (4, 5), (5, 6), (6, 8),     # nose → left ear
    (9, 10),                              # mouth
    # Torso
    (11, 12),                             # shoulders
    (11, 23), (12, 24),                   # shoulders → hips
    (23, 24),                             # hips
    # Right arm
    (12, 14), (14, 16),                   # shoulder → elbow → wrist
    (16, 18), (16, 20), (16, 22),         # wrist → fingers
    # Left arm
    (11, 13), (13, 15),                   # shoulder → elbow → wrist
    (15, 17), (15, 19), (15, 21),         # wrist → fingers
    # Right leg
    (24, 26), (26, 28),                   # hip → knee → ankle
    (28, 30), (28, 32),                   # ankle → foot
    # Left leg
    (23, 25), (25, 27),                   # hip → knee → ankle
    (27, 29), (27, 31),                   # ankle → foot
]

NUM_JOINTS = 33


def _build_adjacency_matrix() -> torch.Tensor:
    """
    Build the normalized adjacency matrix for the MediaPipe skeleton graph.

    Uses the symmetric normalization: Â = D^{-1/2} A D^{-1/2}
    where A includes self-loops.
    """
    A = np.zeros((NUM_JOINTS, NUM_JOINTS), dtype=np.float32)

    # Self-loops
    for i in range(NUM_JOINTS):
        A[i, i] = 1.0

    # Bone connections (symmetric)
    for (i, j) in _MEDIAPIPE_EDGES:
        A[i, j] = 1.0
        A[j, i] = 1.0

    # Symmetric normalization: D^{-1/2} A D^{-1/2}
    D = np.sum(A, axis=1)
    D_inv_sqrt = np.diag(1.0 / np.sqrt(D + 1e-8))
    A_norm = D_inv_sqrt @ A @ D_inv_sqrt

    return torch.from_numpy(A_norm)


class GraphConv(nn.Module):
    """
    Spatial graph convolution layer.

    Multiplies the adjacency matrix with node features, then applies
    a pointwise 1×1 convolution to mix channels.
    """

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C_in, T, V) — features per joint per frame.
            A: (V, V) — normalized adjacency matrix.

        Returns:
            (B, C_out, T, V) — graph-convolved features.
        """
        # Graph convolution: multiply features by adjacency
        # x shape: (B, C, T, V) → einsum over joint dimension
        x = torch.einsum("bctv,vw->bctw", x, A)
        # Pointwise conv to mix channels
        x = self.conv(x)
        return x


class STGCNBlock(nn.Module):
    """
    Single ST-GCN block: spatial graph conv → temporal conv → residual.

    Applies graph convolution (spatial) followed by a 1D temporal
    convolution along the time axis, with batch norm and dropout.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        temporal_kernel: int = 9,
        stride: int = 1,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.gcn = GraphConv(in_channels, out_channels)
        self.bn_spatial = nn.BatchNorm2d(out_channels)

        # Temporal convolution (operates along time axis)
        padding = (temporal_kernel - 1) // 2
        self.tcn = nn.Conv2d(
            out_channels,
            out_channels,
            kernel_size=(temporal_kernel, 1),
            stride=(stride, 1),
            padding=(padding, 0),
        )
        self.bn_temporal = nn.BatchNorm2d(out_channels)
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU(inplace=True)

        # Residual connection (with projection if dimensions change)
        if in_channels != out_channels or stride != 1:
            self.residual = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=(stride, 1)),
                nn.BatchNorm2d(out_channels),
            )
        else:
            self.residual = nn.Identity()

    def forward(self, x: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C_in, T, V)
            A: (V, V)

        Returns:
            (B, C_out, T', V) — T' may differ if stride > 1.
        """
        res = self.residual(x)

        # Spatial graph convolution
        x = self.gcn(x, A)
        x = self.bn_spatial(x)
        x = self.relu(x)

        # Temporal convolution
        x = self.tcn(x)
        x = self.bn_temporal(x)
        x = self.dropout(x)

        # Residual + activation
        x = self.relu(x + res)
        return x


class STGCN(nn.Module):
    """
    ST-GCN backbone network.

    Stacks multiple ST-GCN blocks with increasing channel width,
    then applies global average pooling to produce a fixed-length
    feature vector regardless of input sequence length.

    Default architecture: 3 → 64 → 128 → 256 channels
    Output: (B, 256) feature vector
    """

    def __init__(
        self,
        in_channels: int = 3,
        block_channels: list[int] | None = None,
        temporal_kernel: int = 9,
        dropout: float = 0.1,
    ):
        super().__init__()

        if block_channels is None:
            block_channels = [64, 128, 256]

        # Register adjacency matrix as a buffer (moves with device, not a parameter)
        A = _build_adjacency_matrix()
        self.register_buffer("A", A)

        # Build ST-GCN blocks
        self.blocks = nn.ModuleList()
        channels = [in_channels] + block_channels
        for i in range(len(block_channels)):
            self.blocks.append(
                STGCNBlock(
                    in_channels=channels[i],
                    out_channels=channels[i + 1],
                    temporal_kernel=temporal_kernel,
                    stride=1,
                    dropout=dropout,
                )
            )

        self.feature_dim = block_channels[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 3, T, 33) — normalized skeleton sequences.

        Returns:
            (B, feature_dim) — global feature vector.
        """
        # Pass through ST-GCN blocks
        for block in self.blocks:
            x = block(x, self.A)

        # Global average pooling over time and joints → (B, C)
        x = x.mean(dim=[2, 3])

        return x
