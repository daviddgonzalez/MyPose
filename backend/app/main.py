"""
PKE Backend — FastAPI Application Factory.

Lifespan context manager handles startup/shutdown:
  - Startup: initialize Supabase client, load ML model (when available)
  - Shutdown: cleanup resources
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_calibration import router as calibration_router
from app.api.routes_evaluate import router as evaluate_router
from app.api.routes_auth import router as auth_router
from app.api.routes_progress import router as progress_router
from app.api.routes_upload import router as upload_router
from app.api.ws_live import router as ws_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────
    print(f" PKE Backend starting on {settings.api_host}:{settings.api_port}")
    print(f"   Device: {settings.model_device}")
    print(f"   Embedding dim: {settings.embedding_dim}")
    print(f"   Deviation threshold: {settings.deviation_threshold}")

    # Store shared state in app.state for access in routes
    app.state.device = settings.model_device

    # Load ST-GCN model from checkpoint (if available)
    import os
    from app.ml.model import PKEModel

    checkpoint = settings.checkpoint_path
    if os.path.isfile(checkpoint):
        try:
            app.state.model = PKEModel.from_checkpoint(
                checkpoint,
                device=settings.model_device,
                block_channels=settings.stgcn_block_channels,
                hidden_dim=settings.projection_hidden_dim,
                embedding_dim=settings.embedding_dim,
            )
            print(f"   ✓ Model loaded from {checkpoint}")
        except Exception as e:
            print(f"   ✗ Failed to load model: {e}")
            app.state.model = None
    else:
        print(f"   [WARN] No checkpoint found at {checkpoint} - running heuristic-only mode")
        app.state.model = None

    yield

    # ── Shutdown ─────────────────────────────────────────
    print(" PKE Backend shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title="PKE — Personalized Kinematic Evaluator",
        description=(
            "Asynchronous CV pipeline for evaluating human movement "
            "against a user-calibrated biomechanical baseline."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────
    application.include_router(upload_router, prefix="/api/v1", tags=["Upload"])
    application.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
    application.include_router(calibration_router, prefix="/api/v1", tags=["Calibration"])
    application.include_router(evaluate_router, prefix="/api/v1", tags=["Evaluation"])
    application.include_router(progress_router, prefix="/api/v1", tags=["Progress"])
    application.include_router(ws_router, prefix="/ws/v1", tags=["WebSocket"])

    # ── Health Check ─────────────────────────────────────
    @application.get("/health", tags=["System"])
    async def health_check():
        """Liveness probe for Docker / load balancers."""
        return {
            "status": "healthy",
            "device": settings.model_device,
            "model_loaded": application.state.model is not None,
        }

    return application


# Module-level app instance for uvicorn
app = create_app()
