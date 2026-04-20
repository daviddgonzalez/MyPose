"""
Path A: WebSocket Live Streaming Endpoint.

Receives real-time MediaPipe landmarks from the browser,
buffers into sliding windows, and returns per-rep evaluation results.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.analysis import analyze_session

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Live landmark streaming endpoint.

    Protocol:
    - Client sends JSON frames: {"type": "frame", "frame_idx": int, "landmarks": [[x,y,z], ...]}
    - Server buffers frames into a sliding window
    - When a rep is detected, server sends back evaluation result
    - Client sends {"type": "end"} to close the session
    - Server runs analysis on buffered frames and sends "session_feedback" + "session_end"
    """
    await websocket.accept()
    frame_buffer: list[dict] = []

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)

            msg_type = message.get("type", "frame")

            if msg_type == "end":
                # ── Run end-of-session analysis ──────────────────────
                feedback = analyze_session(frame_buffer)

                # Send the feedback message (rich analysis data)
                feedback_dict = asdict(feedback)
                feedback_dict["type"] = "session_feedback"
                await websocket.send_json(feedback_dict)

                # Then send the session_end message (signals completion)
                await websocket.send_json({
                    "type": "session_end",
                    "total_frames": len(frame_buffer),
                    "message": "Session ended.",
                })
                break

            if msg_type == "frame":
                frame_buffer.append(message)

                # TODO (Phase 7): Implement sliding window + rep detection
                # ML-READY: When rep detection is implemented, call
                # analyze_rep(window) here and send WSResultMessage back.
                # For now, send back an acknowledgement every 30 frames
                if len(frame_buffer) % 30 == 0:
                    await websocket.send_json({
                        "type": "ack",
                        "frames_received": len(frame_buffer),
                        "message": f"Buffered {len(frame_buffer)} frames.",
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected. Total frames: {len(frame_buffer)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
