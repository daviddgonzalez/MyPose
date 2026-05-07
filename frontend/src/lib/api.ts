/**
 * Typed fetch wrappers for PKE backend REST API endpoints.
 * Base URL is configurable via NEXT_PUBLIC_API_URL environment variable.
 */

import type {
  AuthUserRequest,
  AuthUserResponse,
  CalibrationFinalizeResponse,
  CalibrationSequenceRequest,
  CalibrationStartResponse,
  EvaluationRequest,
  EvaluationResponse,
  ProgressCheckinRequest,
  ProgressCheckinResponse,
  ProgressSummaryResponse,
  TaskStatusResponse,
  UploadResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.trim() || "";

function buildApiErrorMessage(path: string, status: number, body: string): string {
  const normalized = body.trim();

  // Handle HTML error pages (commonly from wrong base URL hitting frontend app).
  if (normalized.startsWith("<!DOCTYPE html") || normalized.startsWith("<html")) {
    return `API ${status}: Backend endpoint not found for ${path}. Check frontend rewrite BACKEND_API_URL (or NEXT_PUBLIC_API_URL) and ensure backend /api routes are running.`;
  }

  // Handle JSON-style FastAPI errors.
  try {
    const parsed = JSON.parse(normalized) as { detail?: string };
    if (parsed?.detail) {
      return `API ${status}: ${parsed.detail}`;
    }
  } catch {
    // Fall back to raw text below.
  }

  return `API ${status}: ${normalized}`;
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(buildApiErrorMessage(path, res.status, body));
  }

  return res.json() as Promise<T>;
}

// ─── Upload ───────────────────────────────────────────────

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE_URL}/api/v1/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed (${res.status}): ${body}`);
  }

  return res.json() as Promise<UploadResponse>;
}

export async function getUploadStatus(
  taskId: string
): Promise<TaskStatusResponse> {
  return request<TaskStatusResponse>(
    `/api/v1/upload/${taskId}/status`
  );
}

export async function getUploadResult(taskId: string): Promise<{
  task_id: string;
  raw_frame_count: number;
  raw_landmarks_shape: number[];
  normalized_tensor_shape: number[];
  message: string;
}> {
  return request(`/api/v1/upload/${taskId}/result`);
}

// ─── Calibration ──────────────────────────────────────────

export async function startCalibration(
  userId: string,
  exerciseName: string
): Promise<CalibrationStartResponse> {
  return request<CalibrationStartResponse>("/api/v1/calibrate/start", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      exercise_name: exerciseName,
    }),
  });
}

export async function addCalibrationSequence(
  sessionId: string,
  data: CalibrationSequenceRequest
): Promise<{
  sequence_id: string;
  session_id: string;
  total_sequences: number;
  message: string;
}> {
  return request(`/api/v1/calibrate/${sessionId}/sequence`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function finalizeCalibration(
  sessionId: string
): Promise<CalibrationFinalizeResponse> {
  return request<CalibrationFinalizeResponse>(
    `/api/v1/calibrate/${sessionId}/finalize`,
    { method: "POST" }
  );
}

// ─── Evaluation ───────────────────────────────────────────

export async function evaluateMovement(
  req: EvaluationRequest
): Promise<EvaluationResponse> {
  return request<EvaluationResponse>("/api/v1/evaluate", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ─── Progress ───────────────────────────────────────────────

export async function createProgressCheckin(
  req: ProgressCheckinRequest
): Promise<ProgressCheckinResponse> {
  return request<ProgressCheckinResponse>("/api/v1/progress/checkin", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getProgressSummary(
  userId: string,
  exerciseName: string,
  days = 14
): Promise<ProgressSummaryResponse> {
  const params = new URLSearchParams({
    user_id: userId,
    exercise_name: exerciseName,
    days: String(days),
  });
  return request<ProgressSummaryResponse>(`/api/v1/progress/summary?${params.toString()}`);
}

// ─── Auth ───────────────────────────────────────────────────

export async function registerUser(req: AuthUserRequest): Promise<AuthUserResponse> {
  return request<AuthUserResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function loginUser(req: AuthUserRequest): Promise<AuthUserResponse> {
  return request<AuthUserResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
