"""
Pose Extraction Service (Path B — MVP).

Takes a video file (local path or Supabase Storage path),
runs MediaPipe Pose frame-by-frame, and outputs a landmark array.

Output shape: (T, 33, 4) where:
    T = number of valid frames
    33 = MediaPipe Pose landmarks
    4 = (x, y, z, visibility)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)



def extract_landmarks_from_video(
    video_path: str,
    target_fps: Optional[int] = None,
    visibility_threshold: Optional[float] = None,
    model_complexity: int = 2,
) -> np.ndarray:
    """
    Extract MediaPipe Pose landmarks from every frame of a video.

    Args:
        video_path: Absolute path to the video file.
        target_fps: Desired output FPS. If the source FPS is higher,
                    frames will be uniformly sampled down. Defaults to settings.target_fps.
        visibility_threshold: Minimum average visibility to keep a frame.
                              Defaults to settings.visibility_threshold.
        model_complexity: MediaPipe model complexity (0=lite, 1=full, 2=heavy).
                          Higher = more accurate but slower. Default 2 for best quality.

    Returns:
        np.ndarray of shape (T, 33, 4) — filtered frames × joints × (x, y, z, visibility).

    Raises:
        FileNotFoundError: If video_path doesn't exist.
        ValueError: If no valid frames could be extracted.
    """
    if target_fps is None:
        target_fps = settings.target_fps
    if visibility_threshold is None:
        visibility_threshold = settings.visibility_threshold

    video_path = str(Path(video_path).resolve())
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = max(1, int(round(source_fps / target_fps)))

    logger.info(
        f"Extracting landmarks: {video_path} | "
        f"{total_frames} frames @ {source_fps:.1f}fps | "
        f"sampling every {frame_interval} frames → ~{target_fps}fps output"
    )

    all_landmarks: list[np.ndarray] = []
    frame_idx = 0

    _mp_pose = mp.solutions.pose
    with _mp_pose.Pose(
        static_image_mode=False,
        model_complexity=model_complexity,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Sample at target FPS
            if frame_idx % frame_interval != 0:
                frame_idx += 1
                continue

            # MediaPipe requires RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)

            if results.pose_landmarks:
                # Extract 33 landmarks → (33, 4) array
                frame_landmarks = np.array([
                    [lm.x, lm.y, lm.z, lm.visibility]
                    for lm in results.pose_landmarks.landmark
                ])

                # Filter by average visibility
                avg_visibility = frame_landmarks[:, 3].mean()
                if avg_visibility >= visibility_threshold:
                    all_landmarks.append(frame_landmarks)

            frame_idx += 1

    cap.release()

    if not all_landmarks:
        raise ValueError(
            f"No valid frames extracted from {video_path}. "
            f"Check video content or lower visibility_threshold (current: {visibility_threshold})."
        )

    landmarks_array = np.stack(all_landmarks, axis=0)  # (T, 33, 4)

    logger.info(
        f"Extraction complete: {landmarks_array.shape[0]} valid frames "
        f"from {total_frames} total ({landmarks_array.shape[0]/total_frames*100:.1f}% retained)"
    )

    return landmarks_array


def extract_landmarks_from_frames(
    frames: list[dict],
) -> np.ndarray:
    """
    Convert raw landmark dicts (from WebSocket Path A) to numpy array.

    This normalizes the format so both Path A (live) and Path B (video)
    produce identical outputs for downstream processing.

    Args:
        frames: List of frame dicts with 'landmarks' key containing
                [[x, y, z], ...] or [[x, y, z, visibility], ...].

    Returns:
        np.ndarray of shape (T, 33, 4).
    """
    all_landmarks = []
    for frame in frames:
        lms = frame.get("landmarks", [])
        frame_arr = []
        for lm in lms:
            if len(lm) == 3:
                frame_arr.append([lm[0], lm[1], lm[2], 1.0])  # Default visibility=1
            elif len(lm) >= 4:
                frame_arr.append([lm[0], lm[1], lm[2], lm[3]])
            else:
                frame_arr.append([0.0, 0.0, 0.0, 0.0])
        all_landmarks.append(frame_arr)

    return np.array(all_landmarks, dtype=np.float32)  # (T, 33, 4)


def frames_to_array(frames) -> np.ndarray:
    """
    Convert a list of Pydantic FrameData objects (from REST input) to numpy.

    Returns (T, 33, 4) — same shape as extract_landmarks_from_frames.
    """
    all_landmarks = []
    for frame in frames:
        all_landmarks.append([[lm.x, lm.y, lm.z, lm.visibility] for lm in frame.landmarks])
    return np.array(all_landmarks, dtype=np.float32)
