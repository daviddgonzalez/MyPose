"""
Path B: Video Upload Routes (MVP Fallback).

Handles pre-recorded .mp4 uploads → local temp storage → async extraction → normalization.
For the MVP, videos are saved locally. Supabase Storage integration is available but optional.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form, Request

from app.config import settings
from app.services.extraction import extract_landmarks_from_video
from app.services.normalization import normalize_landmarks
from app.utils.schemas import TaskStatus, TaskStatusResponse, UploadResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory task registry (swap for Redis/DB in production)
_tasks: Dict[str, TaskStatusResponse] = {}

# Store extracted data (in production, this goes to Supabase)
_extraction_results: Dict[str, dict] = {}


async def _process_video(
    task_id: str,
    local_path: str,
    model: object | None = None,
    user_id: Optional[str] = None,
    exercise_name: Optional[str] = None,
):
    """
    Background task: extract landmarks from video, normalize, and optionally
    evaluate against the user's calibration centroid.

    Updates task status as it progresses through the pipeline.
    """
    try:
        # Update status: processing
        _tasks[task_id].status = TaskStatus.PROCESSING
        _tasks[task_id].message = "Extracting pose landmarks..."
        _tasks[task_id].progress = 0.1

        # Step 1: Extract landmarks (CPU-intensive, run in thread pool)
        loop = asyncio.get_event_loop()
        landmarks = await loop.run_in_executor(
            None,
            extract_landmarks_from_video,
            local_path,
        )
        # landmarks shape: (T, 33, 4)

        _tasks[task_id].progress = 0.6
        _tasks[task_id].landmarks_extracted = landmarks.shape[0]
        _tasks[task_id].message = f"Extracted {landmarks.shape[0]} frames. Normalizing..."

        # Step 2: Normalize for model input
        normalized = await loop.run_in_executor(
            None,
            normalize_landmarks,
            landmarks,
        )
        # normalized shape: (1, 3, 64, 33)

        _tasks[task_id].progress = 0.9
        _tasks[task_id].message = "Normalization complete."

        # Store results
        _extraction_results[task_id] = {
            "raw_landmarks": landmarks,       # (T, 33, 4)
            "normalized_tensor": normalized,  # (1, 3, 64, 33)
            "raw_frame_count": landmarks.shape[0],
        }

        # Step 3 (optional): Auto-evaluate against user calibration.
        # Only runs when the caller supplied user_id + exercise_name AND the
        # model is loaded. Errors here don't fail the extraction task.
        if model is not None and user_id and exercise_name:
            try:
                from app.api.routes_evaluate import run_evaluation
                evaluation = await run_evaluation(
                    user_id=user_id,
                    exercise_name=exercise_name,
                    landmarks_arr=landmarks,
                    model=model,
                )
                _tasks[task_id].evaluation = evaluation
                _extraction_results[task_id]["evaluation"] = evaluation
                logger.info(
                    f"Task {task_id}: evaluation passed={evaluation.passed} "
                    f"distance={evaluation.distance_to_centroid:.4f}"
                )
            except Exception as e:
                logger.warning(f"Task {task_id}: auto-evaluation failed (non-fatal): {e}")

        # Update status: complete
        _tasks[task_id].status = TaskStatus.COMPLETE
        _tasks[task_id].progress = 1.0
        _tasks[task_id].message = (
            f"Pipeline complete. {landmarks.shape[0]} frames extracted, "
            f"normalized to {normalized.shape} tensor."
        )

        logger.info(f"Task {task_id}: Pipeline complete. Output shape: {normalized.shape}")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        _tasks[task_id].status = TaskStatus.FAILED
        _tasks[task_id].message = f"Extraction failed: {str(e)}"

    finally:
        # Cleanup temp file
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except OSError:
            pass


@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(default=None),
    exercise_name: Optional[str] = Form(default=None),
):
    """
    Upload an .mp4 video for asynchronous pose extraction.

    The video is saved locally and processed in the background via MediaPipe.
    Poll the status endpoint to track progress. When `user_id` and
    `exercise_name` are provided AND the user has calibrated, the task
    additionally produces an evaluation against their baseline.
    """
    # Validate file type
    if file.content_type not in ("video/mp4", "video/mpeg", "video/quicktime"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Only .mp4 is accepted.",
        )

    task_id = str(uuid.uuid4())

    # Save to a temp file for background processing
    temp_dir = tempfile.mkdtemp(prefix="pke_upload_")
    local_path = os.path.join(temp_dir, file.filename or f"{task_id}.mp4")

    contents = await file.read()
    with open(local_path, "wb") as f:
        f.write(contents)

    file_size_mb = len(contents) / (1024 * 1024)
    logger.info(f"Task {task_id}: Received '{file.filename}' ({file_size_mb:.1f} MB)")

    # Register the task
    _tasks[task_id] = TaskStatusResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"Video '{file.filename}' received ({file_size_mb:.1f} MB). Queued for processing.",
    )

    # Snapshot the model handle here so the background task doesn't depend on
    # the Request object outlasting the response.
    model = getattr(request.app.state, "model", None)

    # Enqueue background extraction (+ optional evaluation)
    background_tasks.add_task(
        _process_video,
        task_id,
        local_path,
        model,
        user_id,
        exercise_name,
    )

    return UploadResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"Video '{file.filename}' received. Task ID: {task_id}",
    )


@router.get("/upload/{task_id}/status", response_model=TaskStatusResponse)
async def get_upload_status(task_id: str):
    """Poll the status of a video extraction task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return _tasks[task_id]


@router.get("/upload/{task_id}/result")
async def get_upload_result(task_id: str):
    """
    Get the extraction result (landmark metadata) for a completed task.

    The actual tensors are kept in memory; this returns metadata about them.
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    task = _tasks[task_id]
    if task.status != TaskStatus.COMPLETE:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not complete. Current status: {task.status}",
        )

    result = _extraction_results.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result data not found.")

    return {
        "task_id": task_id,
        "raw_frame_count": result["raw_frame_count"],
        "raw_landmarks_shape": list(result["raw_landmarks"].shape),
        "normalized_tensor_shape": list(result["normalized_tensor"].shape),
        "evaluation": result.get("evaluation"),
        "message": "Extraction complete. Ready for evaluation.",
    }
