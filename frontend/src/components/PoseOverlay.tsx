"use client";

import { useEffect, useRef } from "react";

interface PoseOverlayProps {
  /** Array of 33 landmarks with x, y, z (normalized 0-1). */
  landmarks: { x: number; y: number; z: number }[] | null;
  /** Width of the video/canvas. */
  width: number;
  /** Height of the video/canvas. */
  height: number;
  /** Optional: highlight specific joints in red (by index). */
  errorJoints?: number[];
}

// MediaPipe Pose connections (pairs of landmark indices)
const POSE_CONNECTIONS: [number, number][] = [
  // Face
  [0, 1], [1, 2], [2, 3], [3, 7],
  [0, 4], [4, 5], [5, 6], [6, 8],
  // Torso
  [9, 10],
  [11, 12],
  [11, 23], [12, 24],
  [23, 24],
  // Left arm
  [11, 13], [13, 15],
  [15, 17], [15, 19], [15, 21],
  [17, 19],
  // Right arm
  [12, 14], [14, 16],
  [16, 18], [16, 20], [16, 22],
  [18, 20],
  // Left leg
  [23, 25], [25, 27],
  [27, 29], [27, 31], [29, 31],
  // Right leg
  [24, 26], [26, 28],
  [28, 30], [28, 32], [30, 32],
];

export default function PoseOverlay({
  landmarks,
  width,
  height,
  errorJoints = [],
}: PoseOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = width;
    canvas.height = height;
    ctx.clearRect(0, 0, width, height);

    if (!landmarks) return;



    const errorSet = new Set(errorJoints);

    // Draw connections
    for (const [i, j] of POSE_CONNECTIONS) {
      if (i >= landmarks.length || j >= landmarks.length) continue;

      const a = landmarks[i];
      const b = landmarks[j];

      const hasError = errorSet.has(i) || errorSet.has(j);

      ctx.beginPath();
      ctx.moveTo(a.x * width, a.y * height);
      ctx.lineTo(b.x * width, b.y * height);
      ctx.strokeStyle = hasError
        ? "rgba(239, 68, 68, 0.8)"
        : "rgba(99, 102, 241, 0.6)";
      ctx.lineWidth = hasError ? 3 : 2;
      ctx.stroke();
    }

    // Draw joints
    for (let i = 0; i < landmarks.length; i++) {
      const lm = landmarks[i];
      const hasError = errorSet.has(i);

      ctx.beginPath();
      ctx.arc(lm.x * width, lm.y * height, hasError ? 5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = hasError
        ? "rgba(239, 68, 68, 1)"
        : "rgba(129, 140, 248, 1)";
      ctx.fill();

      if (hasError) {
        ctx.beginPath();
        ctx.arc(lm.x * width, lm.y * height, 8, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(239, 68, 68, 0.4)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  }, [landmarks, width, height, errorJoints]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute top-0 left-0 pointer-events-none -scale-x-100"
      style={{ width, height }}
    />
  );
}
