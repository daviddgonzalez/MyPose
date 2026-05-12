"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import WebcamCapture from "./WebcamCapture";
import { EXERCISES } from "@/lib/exercises";
import {
  startCalibration,
  addCalibrationSequence,
  finalizeCalibration,
} from "@/lib/api";
import type { FrameData, Landmark } from "@/lib/types";
import { getStoredUser } from "@/lib/user";

type Step = "select" | "record" | "review" | "finalize";

const MIN_SEQUENCE_SECONDS = 5;
const MIN_TOTAL_SECONDS = 30;
const MAX_SEQUENCES = 8;

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
  const [userId, setUserId] = useState<string>("dev-user");
  const recordingStartRef = useRef<number | null>(null);
  const [, setNow] = useState(0); // 1Hz tick so the live recording timer re-renders

  // Drive a 1Hz re-render only while recording, for the live timer.
  useEffect(() => {
    if (!isRecording) return;
    const handle = setInterval(() => setNow((n) => n + 1), 250);
    return () => clearInterval(handle);
  }, [isRecording]);

  const totalSeconds = sequences.reduce((sum, s) => sum + s.duration, 0);
  const currentSeqSeconds = isRecording && recordingStartRef.current
    ? (Date.now() - recordingStartRef.current) / 1000
    : 0;
  const canFinalize = totalSeconds >= MIN_TOTAL_SECONDS;
  const totalPct = Math.min(100, (totalSeconds / MIN_TOTAL_SECONDS) * 100);

  useEffect(() => {
    const activeUser = getStoredUser();
    if (activeUser?.userId) {
      setUserId(activeUser.userId);
    }
  }, []);

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
      const res = await startCalibration(userId, selectedExercise);
      setSessionId(res.session_id);
      setStep("record");
      setStatusMsg(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start calibration");
    }
  }, [selectedExercise, userId]);

  const handleStartRecording = useCallback(() => {
    setCurrentFrames([]);
    recordingStartRef.current = Date.now();
    setIsRecording(true);
    setStatusMsg(
      `Recording… perform the exercise with correct form (min ${MIN_SEQUENCE_SECONDS}s per take)`
    );
  }, []);

  const handleStopRecording = useCallback(async () => {
    const startedAt = recordingStartRef.current ?? Date.now();
    const elapsed = (Date.now() - startedAt) / 1000;
    recordingStartRef.current = null;
    setIsRecording(false);

    if (elapsed < MIN_SEQUENCE_SECONDS) {
      setStatusMsg(
        `Take was only ${elapsed.toFixed(1)}s — need at least ${MIN_SEQUENCE_SECONDS}s. Discarded; try again.`
      );
      setCurrentFrames([]);
      return;
    }
    if (currentFrames.length < 10) {
      setStatusMsg("Too few frames captured — check webcam permissions and try again.");
      setCurrentFrames([]);
      return;
    }

    const newSeq: RecordedSequence = {
      id: sequences.length + 1,
      frames: [...currentFrames],
      duration: elapsed,
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

    const nextTotal = totalSeconds + elapsed;
    setSequences((prev) => [...prev, newSeq]);
    setCurrentFrames([]);

    if (nextTotal >= MIN_TOTAL_SECONDS) {
      setStatusMsg(
        `Calibration is ready (${nextTotal.toFixed(1)}s of ${MIN_TOTAL_SECONDS}s recorded). Add more reps or click Review.`
      );
    } else {
      setStatusMsg(
        `${nextTotal.toFixed(1)}s / ${MIN_TOTAL_SECONDS}s recorded — keep going.`
      );
    }
  }, [currentFrames, sequences, sessionId, totalSeconds]);

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
            <div className="border-l-4 border-[var(--pke-accent)] bg-[var(--pke-bg-surface)] p-4 space-y-2 rounded-r-md">
              <p className="text-[10px] font-extrabold uppercase tracking-widest text-[var(--pke-accent)]">
                Personalization is optional
              </p>
              <p className="text-sm text-[var(--pke-text-secondary)] leading-relaxed">
                <strong className="text-[var(--pke-text-primary)]">What it adds:</strong> a
                second feedback score — <em>Personal match</em> — that tells you whether a session
                looks like the way <em>you</em> normally do this exercise. The always-on
                <em> Textbook score</em> (generic ROM &amp; stability) keeps working without this.
              </p>
              <p className="text-sm text-[var(--pke-text-secondary)] leading-relaxed">
                <strong className="text-[var(--pke-text-primary)]">When to skip:</strong> you do
                the exercise traditionally and want plain textbook-form grading.
                <strong className="text-[var(--pke-text-primary)]"> When to do it:</strong> your
                body diverges from generic targets (mobility, proportions) or you want to track
                consistency against your own baseline.
              </p>
              <p className="text-sm text-[var(--pke-text-secondary)] leading-relaxed">
                <strong className="text-[var(--pke-text-primary)]">Cost:</strong> ~30 seconds of
                recording, split into takes of at least 5 seconds each.
              </p>
            </div>

            <h3 className="text-lg font-semibold text-[var(--pke-text-primary)] pt-2">
              Choose an Exercise
            </h3>
            <p className="text-sm text-[var(--pke-text-secondary)]">
              Select the exercise you want to personalize. You&apos;ll record at least 30 seconds
              of correct form to create your baseline.
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
                  {totalSeconds.toFixed(1)}s / {MIN_TOTAL_SECONDS}s recorded — min {MIN_SEQUENCE_SECONDS}s per take
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
                        Record Take {sequences.length + 1}
                      </button>
                    )}
                    {canFinalize && (
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

            {/* Total-duration progress bar */}
            <div className="space-y-1">
              <div className="pke-progress">
                <div
                  className="pke-progress-bar"
                  style={{
                    width: `${totalPct}%`,
                    background: canFinalize ? 'var(--pke-success)' : undefined,
                  }}
                />
              </div>
              <p className="text-[10px] text-[var(--pke-text-muted)] uppercase tracking-widest">
                {canFinalize
                  ? `Threshold met — ${totalSeconds.toFixed(1)}s of ${MIN_TOTAL_SECONDS}s`
                  : `${(MIN_TOTAL_SECONDS - totalSeconds).toFixed(1)}s to go`}
              </p>
            </div>

            {/* Recording indicator */}
            {isRecording && (
              <div className="flex items-center gap-3 text-sm">
                <span className="w-3 h-3 rounded-full bg-[var(--pke-danger)] animate-pulse" />
                <span className="text-[var(--pke-danger)] font-medium">
                  Recording — {currentSeqSeconds.toFixed(1)}s
                  {currentSeqSeconds < MIN_SEQUENCE_SECONDS && (
                    <span className="ml-2 text-[var(--pke-text-muted)] font-normal">
                      (need {(MIN_SEQUENCE_SECONDS - currentSeqSeconds).toFixed(1)}s more)
                    </span>
                  )}
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
              You&apos;ve recorded {totalSeconds.toFixed(1)}s across {sequences.length} take{sequences.length === 1 ? "" : "s"}. Review
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
                disabled={finalizing || !canFinalize}
                title={!canFinalize ? `Need ${MIN_TOTAL_SECONDS}s total — you have ${totalSeconds.toFixed(1)}s` : undefined}
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
              <a href="/" className="pke-btn pke-btn-secondary">
                Home
              </a>
              <a
                href={selectedExercise ? `/catalog/${selectedExercise}` : "/"}
                className="pke-btn pke-btn-primary"
              >
                Back to Exercise
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
