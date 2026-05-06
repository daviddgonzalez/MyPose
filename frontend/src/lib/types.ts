/**
 * TypeScript types mirroring backend Pydantic schemas.
 * Keep in sync with backend/app/utils/schemas.py
 */

// ─── Enums ────────────────────────────────────────────────

export enum TaskStatus {
  PENDING = "pending",
  PROCESSING = "processing",
  COMPLETE = "complete",
  FAILED = "failed",
}

export enum CalibrationStatus {
  PENDING = "pending",
  PROCESSING = "processing",
  COMPLETE = "complete",
  FAILED = "failed",
}

export type StrictnessLevel = "lenient" | "moderate" | "strict" | "drill_sergeant";

// ─── Landmark Data ────────────────────────────────────────

export interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility?: number;
}

export interface FrameData {
  frame_idx: number;
  landmarks: Landmark[];
}

// ─── Upload ───────────────────────────────────────────────

export interface UploadResponse {
  task_id: string;
  status: TaskStatus;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  progress: number;
  message: string;
  landmarks_extracted?: number | null;
}

// ─── Calibration ──────────────────────────────────────────

export interface CalibrationStartRequest {
  user_id: string;
  exercise_name: string;
}

export interface CalibrationStartResponse {
  session_id: string;
  status: CalibrationStatus;
  message: string;
}

export interface CalibrationSequenceRequest {
  landmarks?: FrameData[] | null;
  storage_path?: string | null;
}

export interface CalibrationFinalizeResponse {
  session_id: string;
  status: CalibrationStatus;
  centroid_stored: boolean;
  num_sequences: number;
  message: string;
}

// ─── Evaluation ───────────────────────────────────────────

export interface JointError {
  joint_index: number;
  joint_name: string;
  error_score: number;
  description: string;
}

export interface EvaluationRequest {
  user_id: string;
  exercise_name: string;
  landmarks: FrameData[];
}

export interface EvaluationResponse {
  evaluation_id: string;
  passed: boolean;
  distance_to_centroid: number;
  threshold: number;
  joint_errors: JointError[];
  dtw_triggered: boolean;
  message: string;
}

// ─── Progress Tracking ──────────────────────────────────────

export interface ProgressCheckinRequest {
  user_id: string;
  exercise_name: string;
  reps_completed: number;
  average_quality_score: number;
  passed_reps?: number;
  failed_reps?: number;
  duration_seconds?: number;
  notes?: string;
}

export interface ProgressCheckinResponse {
  checkin_id: string;
  user_id: string;
  exercise_name: string;
  reps_completed: number;
  average_quality_score: number;
  created_at: string;
  message: string;
}

export interface ProgressTrendPoint {
  date: string;
  total_reps: number;
  average_quality_score: number;
  checkins: number;
}

export interface ProgressSummaryResponse {
  user_id: string;
  exercise_name: string;
  days: number;
  total_reps: number;
  average_quality_score: number;
  total_checkins: number;
  trend: ProgressTrendPoint[];
}

// ─── Auth (MVP) ────────────────────────────────────────────

export interface AuthUserRequest {
  username: string;
  password: string;
}

export interface AuthUserResponse {
  user_id: string;
  username: string;
  message: string;
}

// ─── WebSocket ────────────────────────────────────────────

export interface WSFrameMessage {
  type: "frame";
  frame_idx: number;
  landmarks: number[][]; // [[x, y, z], ...] — 33 entries
}

export interface WSAckMessage {
  type: "ack";
  frames_received: number;
  message: string;
}

export interface WSConfigMessage {
  type: "config";
  strictness: StrictnessLevel;
  exercise: string;
  user_id?: string;
}

export interface WSResultMessage {
  type: "result";
  rep_idx: number;
  passed: boolean;
  distance: number;
  joint_errors: JointError[];
}

export interface WSSessionEndMessage {
  type: "session_end";
  total_frames: number;
  message: string;
}

export interface JointSummary {
  joint_name: string;
  mean_angle_degrees: number;
  range_of_motion_degrees: number;
  stability_score: number; // 0–1, higher = more consistent
  passed: boolean;
  issues: string[];
}

export interface WSFeedbackMessage {
  type: "session_feedback";
  strictness_level: StrictnessLevel;
  total_frames: number;
  duration_seconds: number;
  joint_summaries: JointSummary[];
  overall_score: number; // 0–100
  message: string;
  // ML-READY: Present when calibration pipeline is active
  passed?: boolean | null;
  distance_to_centroid?: number | null;
  calibration_available: boolean;
}

export type WSIncomingMessage =
  | WSAckMessage
  | WSResultMessage
  | WSSessionEndMessage
  | WSFeedbackMessage;

// ─── Exercise Catalog ─────────────────────────────────────

export interface Exercise {
  slug: string;
  displayName: string;
  description: string;
  targetJoints: string[];
  targetMuscles: string[];
  difficulty: "Beginner" | "Intermediate" | "Advanced";
  icon: string;
  color: string;
}
