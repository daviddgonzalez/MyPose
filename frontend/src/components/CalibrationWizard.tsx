"use client";

import { useCallback, useState } from "react";
import WebcamCapture from "./WebcamCapture";
import { EXERCISES } from "@/lib/exercises";
import {
  startCalibration,
  addCalibrationSequence,
  finalizeCalibration,
} from "@/lib/api";
import type { FrameData, Landmark } from "@/lib/types";

type Step = "select" | "record" | "review" | "finalize";

const REQUIRED_SEQUENCES = 3;
const MAX_SEQUENCES = 5;

interface RecordedSequence {
  id: number;
  frames: FrameData[];
  duration: number;
}

export default function CalibrationWizard({
  preselectedExercise,
}: {
  preselectedExercise?: string;
}) {
  const [step, setStep] = useState<Step>("select");
  const [selectedExercise, setSelectedExercise] = useState(
    preselectedExercise || ""
  );
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sequences, setSequences] = useState<RecordedSequence[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [currentFrames, setCurrentFrames] = useState<FrameData[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [finalizing, setFinalizing] = useState(false);

  const steps: { key: Step; label: string }[] = [
    { key: "select", label: "Select Exercise" },
    { key: "record", label: "Record Sequences" },
    { key: "review", label: "Review" },
    { key: "finalize", label: "Finalize" },
  ];

  const currentStepIdx = steps.findIndex((s) => s.key === step);

  const handleStartCalibration = useCallback(async () => {
    if (!selectedExercise) return;
    setError(null);

    try {
      const res = await startCalibration("dev-user", selectedExercise);
      setSessionId(res.session_id);
      setStep("record");
      setStatusMsg(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start calibration");
    }
  }, [selectedExercise]);

  const handleStartRecording = useCallback(() => {
    setCurrentFrames([]);
    setIsRecording(true);
    setStatusMsg("Recording… perform the exercise with correct form");
  }, []);

  const handleStopRecording = useCallback(async () => {
    setIsRecording(false);

    if (currentFrames.length < 10) {
      setStatusMsg("Too few frames captured. Try again.");
      return;
    }

    const newSeq: RecordedSequence = {
      id: sequences.length + 1,
      frames: [...currentFrames],
      duration: currentFrames.length / 30,
    };

    // Submit sequence to backend
    if (sessionId) {
      try {
        const res = await addCalibrationSequence(sessionId, {
          landmarks: currentFrames,
        });
        setStatusMsg(res.message);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to submit sequence");
        return;
      }
    }

    setSequences((prev) => [...prev, newSeq]);
    setCurrentFrames([]);

    if (sequences.length + 1 >= REQUIRED_SEQUENCES) {
      setStatusMsg(
        `${sequences.length + 1} sequences recorded. You can finalize or record more (max ${MAX_SEQUENCES}).`
      );
    }
  }, [currentFrames, sequences, sessionId]);

  const handleLandmarks = useCallback(
    (landmarks: { x: number; y: number; z: number }[]) => {
      if (!isRecording) return;

      const frame: FrameData = {
        frame_idx: currentFrames.length,
        landmarks: landmarks.map(
          (lm): Landmark => ({
            x: lm.x,
            y: lm.y,
            z: lm.z,
            visibility: 1.0,
          })
        ),
      };

      setCurrentFrames((prev) => [...prev, frame]);
    },
    [isRecording, currentFrames.length]
  );

  const handleFinalize = useCallback(async () => {
    if (!sessionId) return;
    setFinalizing(true);
    setError(null);

    try {
      const res = await finalizeCalibration(sessionId);
      setStep("finalize");
      setStatusMsg(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Finalization failed");
    } finally {
      setFinalizing(false);
    }
  }, [sessionId]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stepper */}
      <div className="flex items-center gap-2">
        {steps.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2 flex-1">
            <div
              className={`pke-step-dot ${
                i < currentStepIdx
                  ? "completed"
                  : i === currentStepIdx
                  ? "active"
                  : ""
              }`}
            >
              {i < currentStepIdx ? i + 1 : i + 1}
            </div>
            <span
              className={`text-xs font-medium hidden sm:inline ${
                i === currentStepIdx
                  ? "text-[var(--pke-text-primary)]"
                  : "text-[var(--pke-text-muted)]"
              }`}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <div
                className={`pke-step-line ${
                  i < currentStepIdx ? "completed" : ""
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="pke-card p-6">
        {/* Step 1: Select Exercise */}
        {step === "select" && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-[var(--pke-text-primary)]">
              Choose an Exercise
            </h3>
            <p className="text-sm text-[var(--pke-text-secondary)]">
              Select the exercise you want to calibrate. You&apos;ll record 3–5
              sequences of correct form to create your personal baseline.
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
              {EXERCISES.map((ex) => (
                <button
                  key={ex.slug}
                  onClick={() => setSelectedExercise(ex.slug)}
                  className={`
                    p-4 rounded-xl text-left transition-all duration-150
                    border
                    ${
                      selectedExercise === ex.slug
                        ? "border-[var(--pke-accent)] bg-[var(--pke-accent-glow)]"
                        : "border-[var(--pke-border)] hover:border-[var(--pke-border-hover)] bg-[var(--pke-bg-surface)]"
                    }
                  `}
                >
                  <span className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white" style={{ background: ex.color }}>{ex.displayName.charAt(0)}</span>
                  <p className="text-sm font-medium text-[var(--pke-text-primary)] mt-2">
                    {ex.displayName}
                  </p>
                  <p className="text-[11px] text-[var(--pke-text-muted)] mt-0.5">
                    {ex.difficulty}
                  </p>
                </button>
              ))}
            </div>

            <button
              onClick={handleStartCalibration}
              disabled={!selectedExercise}
              className="pke-btn pke-btn-primary mt-4"
            >
              Begin Calibration
            </button>
          </div>
        )}

        {/* Step 2: Record Sequences */}
        {step === "record" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-[var(--pke-text-primary)]">
                  Record Sequences
                </h3>
                <p className="text-sm text-[var(--pke-text-secondary)]">
                  {sequences.length}/{MAX_SEQUENCES} recorded (min{" "}
                  {REQUIRED_SEQUENCES})
                </p>
              </div>

              <div className="flex items-center gap-2">
                {isRecording ? (
                  <button
                    onClick={handleStopRecording}
                    className="pke-btn pke-btn-danger pke-btn-sm"
                  >
                    Stop Recording
                  </button>
                ) : (
                  <>
                    {sequences.length < MAX_SEQUENCES && (
                      <button
                        onClick={handleStartRecording}
                        className="pke-btn pke-btn-primary pke-btn-sm"
                      >
                        Record Sequence {sequences.length + 1}
                      </button>
                    )}
                    {sequences.length >= REQUIRED_SEQUENCES && (
                      <button
                        onClick={() => setStep("review")}
                        className="pke-btn pke-btn-secondary pke-btn-sm"
                      >
                        Review
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Recording indicator */}
            {isRecording && (
              <div className="flex items-center gap-2 text-sm">
                <span className="w-3 h-3 rounded-full bg-[var(--pke-danger)] animate-pulse" />
                <span className="text-[var(--pke-danger)] font-medium">
                  Recording — {currentFrames.length} frames
                </span>
              </div>
            )}

            <WebcamCapture
              onLandmarks={handleLandmarks}
              active={isRecording}
              width={560}
              height={420}
            />

            {/* Recorded sequences */}
            {sequences.length > 0 && (
              <div className="space-y-2 mt-4">
                <h4 className="text-sm font-medium text-[var(--pke-text-secondary)]">
                  Recorded Sequences
                </h4>
                {sequences.map((seq) => (
                  <div
                    key={seq.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-[var(--pke-bg-surface)] border border-[var(--pke-border)]"
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-2 h-2 rounded-full bg-[var(--pke-success)]" />
                      <span className="text-sm text-[var(--pke-text-primary)]">
                        Sequence {seq.id}
                      </span>
                    </div>
                    <span className="text-xs text-[var(--pke-text-muted)]">
                      {seq.frames.length} frames • {seq.duration.toFixed(1)}s
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Review */}
        {step === "review" && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-[var(--pke-text-primary)]">
              Review & Finalize
            </h3>
            <p className="text-sm text-[var(--pke-text-secondary)]">
              You&apos;ve recorded {sequences.length} calibration sequences. Review
              and finalize to create your personal baseline.
            </p>

            <div className="space-y-2">
              {sequences.map((seq) => (
                <div
                  key={seq.id}
                  className="flex items-center justify-between p-4 rounded-lg bg-[var(--pke-bg-surface)] border border-[var(--pke-border)]"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-[var(--pke-success)]/15 flex items-center justify-center text-[var(--pke-success)] text-sm font-semibold">
                      {seq.id}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--pke-text-primary)]">
                        Sequence {seq.id}
                      </p>
                      <p className="text-xs text-[var(--pke-text-muted)]">
                        {seq.frames.length} frames •{" "}
                        {seq.duration.toFixed(1)} seconds
                      </p>
                    </div>
                  </div>
                  <span className="pke-badge pke-badge-success">Ready</span>
                </div>
              ))}
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setStep("record")}
                className="pke-btn pke-btn-secondary"
              >
                Back
              </button>
              <button
                onClick={handleFinalize}
                disabled={finalizing}
                className="pke-btn pke-btn-primary"
              >
                {finalizing ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Processing…
                  </>
                ) : (
                  "Finalize Calibration"
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Complete */}
        {step === "finalize" && (
          <div className="text-center py-8 space-y-4">
            <div className="w-16 h-16 mx-auto rounded-full bg-[var(--pke-success)]/15 flex items-center justify-center text-[var(--pke-success)] text-2xl font-bold">OK</div>
            <h3 className="text-xl font-semibold text-[var(--pke-text-primary)]">
              Calibration Submitted
            </h3>
            <p className="text-sm text-[var(--pke-text-secondary)] max-w-md mx-auto">
              {statusMsg ||
                "Your baseline is being computed. This may take a few minutes."}
            </p>
            <div className="flex justify-center gap-3 pt-2">
              <a href="/catalog" className="pke-btn pke-btn-secondary">
                Browse Catalog
              </a>
              <a href="/live" className="pke-btn pke-btn-primary">
                Start Live Session
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Status / Error */}
      {statusMsg && step !== "finalize" && (
        <p className="text-sm text-[var(--pke-text-secondary)]">{statusMsg}</p>
      )}
      {error && (
        <div className="p-3 rounded-lg bg-[rgba(239,68,68,0.1)] border border-[var(--pke-danger)] text-sm text-[var(--pke-danger)]">
          {error}
        </div>
      )}
    </div>
  );
}
