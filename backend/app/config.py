"""
PKE Backend Configuration.

Reads environment variables via Pydantic Settings.
All config is centralized here — no scattered os.getenv() calls.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    default_strictness: str = "moderate"

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
