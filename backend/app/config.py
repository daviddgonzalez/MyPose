"""
PKE Backend Configuration.

Reads environment variables via Pydantic Settings.
All config is centralized here — no scattered os.getenv() calls.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        # Allow running backend either from `backend/` or repo root.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Supabase ───────────────────────────────────────
    supabase_url: str = "https://placeholder.supabase.co"
    supabase_key: str = "placeholder-anon-key"
    supabase_service_role_key: str = "placeholder-service-role-key"

    # ─── Storage ────────────────────────────────────────
    storage_bucket: str = "videos"

    # ─── Model ──────────────────────────────────────────
    model_device: str = "cpu"
    embedding_dim: int = 256
    deviation_threshold: float = 0.15
    checkpoint_dir: str = "checkpoints"
    checkpoint_file: str = "pke_pretrained.pt"
    default_strictness: str = "moderate"

    # ─── ST-GCN / Siamese ──────────────────────────────
    stgcn_channels: str = "64,128,256"  # Comma-separated block channels
    projection_hidden_dim: int = 512
    finetune_lr: float = 1e-4
    finetune_epochs: int = 10

    @property
    def stgcn_block_channels(self) -> list[int]:
        """Parse the comma-separated channel config into a list."""
        return [int(c.strip()) for c in self.stgcn_channels.split(",")]

    @property
    def checkpoint_path(self) -> str:
        """Full path to the model checkpoint file."""
        import os
        return os.path.join(self.checkpoint_dir, self.checkpoint_file)

    # ─── Server ─────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ─── Extraction ─────────────────────────────────────
    target_fps: int = 30
    sequence_length: int = 64  # Frames per normalized sequence
    visibility_threshold: float = 0.5
    num_joints: int = 33


# Singleton — import this everywhere
settings = Settings()
