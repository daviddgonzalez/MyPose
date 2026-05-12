"""
Shared Pydantic schemas for request/response models.

These are the data contracts between frontend and backend.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────


class StrictnessLevel(str, Enum):
    """Feedback strictness levels."""
    LENIENT = "lenient"
    MODERATE = "moderate"
    STRICT = "strict"
    DRILL_SERGEANT = "drill_sergeant"


class TaskStatus(str, Enum):
    """Status of an async processing task."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class CalibrationStatus(str, Enum):
    """Status of a calibration session."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# ─── Landmark Data ──────────────────────────────────────────


class Landmark(BaseModel):
    """Single 3D landmark point."""
    x: float
    y: float
    z: float
    visibility: float = Field(default=1.0, ge=0.0, le=1.0)


class FrameData(BaseModel):
    """Single frame of landmark data from MediaPipe."""
    frame_idx: int = Field(ge=0)
    landmarks: list[Landmark] = Field(min_length=33, max_length=33)


# ─── Upload ─────────────────────────────────────────────────


class UploadResponse(BaseModel):
    """Response after initiating a video upload for processing."""
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = "Video upload received. Processing will begin shortly."


class TaskStatusResponse(BaseModel):
    """Response for polling task status."""
    task_id: str
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="0.0 to 1.0")
    message: str = ""
    landmarks_extracted: Optional[int] = None
    evaluation: Optional["EvaluationResponse"] = None


# ─── Calibration ────────────────────────────────────────────


class CalibrationStartRequest(BaseModel):
    """Request to begin a calibration session."""
    user_id: str
    exercise_name: str


class CalibrationStartResponse(BaseModel):
    """Response after creating a calibration session."""
    session_id: str
    status: CalibrationStatus = CalibrationStatus.PENDING
    message: str = "Calibration session created."


class CalibrationSequenceRequest(BaseModel):
    """Submit a single calibration sequence (landmarks or video reference)."""
    landmarks: Optional[list[FrameData]] = None
    storage_path: Optional[str] = None  # Path in Supabase Storage (MVP upload)


class CalibrationFinalizeResponse(BaseModel):
    """Response after finalizing calibration (fine-tuning + centroid computation)."""
    session_id: str
    status: CalibrationStatus
    centroid_stored: bool = False
    num_sequences: int = 0
    message: str = ""


# ─── Evaluation ─────────────────────────────────────────────


class EvaluationRequest(BaseModel):
    """Request to evaluate a movement sequence against the user's baseline."""
    user_id: str
    exercise_name: str
    landmarks: list[FrameData]


class JointError(BaseModel):
    """Error report for a single joint."""
    joint_index: int
    joint_name: str
    error_score: float = Field(ge=0.0, le=1.0)
    description: str = ""


class EvaluationResponse(BaseModel):
    """Full evaluation result."""
    evaluation_id: str
    passed: bool
    distance_to_centroid: float
    threshold: float
    joint_errors: list[JointError] = []
    dtw_triggered: bool = False
    message: str = ""


# ─── Progress Tracking ────────────────────────────────────────


class ProgressCheckinRequest(BaseModel):
    """Request to record a user's workout progress checkpoint."""
    user_id: str
    exercise_name: str
    reps_completed: int = Field(ge=0)
    average_quality_score: float = Field(ge=0.0, le=100.0)
    passed_reps: int = Field(default=0, ge=0)
    failed_reps: int = Field(default=0, ge=0)
    duration_seconds: Optional[float] = Field(default=None, ge=0.0)
    notes: str = ""


class ProgressCheckinResponse(BaseModel):
    """Response for an accepted progress check-in."""
    checkin_id: str
    user_id: str
    exercise_name: str
    reps_completed: int
    average_quality_score: float
    created_at: str
    message: str = "Progress check-in recorded."


class ProgressTrendPoint(BaseModel):
    """Daily aggregate data point for progress trends."""
    date: str
    total_reps: int
    average_quality_score: float
    checkins: int


class ProgressSummaryResponse(BaseModel):
    """Summary + trend window for a user's exercise progress."""
    user_id: str
    exercise_name: str
    days: int
    total_reps: int
    average_quality_score: float
    total_checkins: int
    trend: list[ProgressTrendPoint] = []


# ─── Auth (MVP) ─────────────────────────────────────────────


class RegisterUserRequest(BaseModel):
    """Create a new app-level user account."""
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginUserRequest(BaseModel):
    """Authenticate an existing app-level user account."""
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class AuthUserResponse(BaseModel):
    """Response payload for login/register operations."""
    user_id: str
    username: str
    message: str


# ─── WebSocket ──────────────────────────────────────────────


class WSFrameMessage(BaseModel):
    """Incoming WebSocket message — a single frame of landmarks."""
    type: str = "frame"
    frame_idx: int
    landmarks: list[list[float]]  # [[x, y, z], ...] — 33 entries


class WSConfigMessage(BaseModel):
    """Incoming WebSocket message — session config."""
    type: str = "config"
    strictness: StrictnessLevel = StrictnessLevel.MODERATE
    exercise: str = "squat"


class WSResultMessage(BaseModel):
    """Outgoing WebSocket message — evaluation result for a rep."""
    type: str = "result"
    rep_idx: int
    passed: bool
    distance: float
    joint_errors: list[JointError] = []


class JointSummarySchema(BaseModel):
    """Per-joint analysis summary from session feedback."""
    joint_name: str
    mean_angle_degrees: float
    range_of_motion_degrees: float
    stability_score: float  # 0–1, higher = more consistent
    combined_score: float = 0.0  # 0–1, min of stability and ROM ratio; agrees with `passed`
    passed: bool = True
    issues: list[str] = []


class WSSessionFeedback(BaseModel):
    """Outgoing WebSocket message — full session analysis feedback."""
    type: str = "session_feedback"
    strictness_level: str
    total_frames: int
    duration_seconds: float
    joint_summaries: list[JointSummarySchema] = []
    overall_score: float = 0.0  # 0–100
    message: str = ""

    # ML-READY: Present when calibration pipeline is active
    passed: Optional[bool] = None
    distance_to_centroid: Optional[float] = None
    calibration_available: bool = False


# Resolve forward reference for TaskStatusResponse.evaluation (declared above).
TaskStatusResponse.model_rebuild()
