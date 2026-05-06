"use client";

import { useEffect, useState } from "react";
import { EXERCISES } from "@/lib/exercises";
import { createProgressCheckin, getProgressSummary } from "@/lib/api";
import { getStoredUser, getUserUpdatedEventName } from "@/lib/user";
import type { ProgressSummaryResponse } from "@/lib/types";

const defaultExercise = EXERCISES[0]?.slug || "squat";

export default function UserProgressPage() {
  const [selectedExercise, setSelectedExercise] = useState(defaultExercise);
  const [summary, setSummary] = useState<ProgressSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [repsCompleted, setRepsCompleted] = useState(10);
  const [qualityScore, setQualityScore] = useState(80);

  const [user, setUser] = useState(() => getStoredUser());

  useEffect(() => {
    const syncUser = () => setUser(getStoredUser());
    window.addEventListener("storage", syncUser);
    window.addEventListener(getUserUpdatedEventName(), syncUser);
    return () => {
      window.removeEventListener("storage", syncUser);
      window.removeEventListener(getUserUpdatedEventName(), syncUser);
    };
  }, []);

  async function loadSummary(exercise: string) {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getProgressSummary(user.userId, exercise, 30);
      setSummary(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load progress.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSummary(selectedExercise);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExercise, user?.userId]);

  async function handleLogCheckin() {
    if (!user) return;
    setStatus("");
    setError(null);
    try {
      await createProgressCheckin({
        user_id: user.userId,
        exercise_name: selectedExercise,
        reps_completed: repsCompleted,
        average_quality_score: qualityScore,
        passed_reps: repsCompleted,
        failed_reps: 0,
        notes: "logged from user progress page",
      });
      setStatus("Check-in saved.");
      await loadSummary(selectedExercise);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save check-in.");
    }
  }

  if (!user) {
    return (
      <div className="px-6 lg:px-12 py-16 max-w-4xl mx-auto w-full animate-fade-in">
        <h1 className="text-4xl font-extrabold text-[var(--pke-text-primary)] mb-3 tracking-tight uppercase">
          My Progress
        </h1>
        <p className="text-sm text-[var(--pke-text-secondary)] mb-8">
          Sign in on the Login page first to access saved progress.
        </p>
        <a href="/login" className="pke-btn pke-btn-primary">Go to Login</a>
      </div>
    );
  }

  const trendPoints = summary?.trend ?? [];
  const hasTrend = trendPoints.length > 0;

  const buildPath = (values: number[], min: number, max: number) => {
    if (values.length === 0) return "";
    const width = 100;
    const height = 100;
    const range = max - min || 1;
    return values
      .map((value, index) => {
        const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width;
        const y = height - ((value - min) / range) * height;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  };

  const qualityValues = trendPoints.map((p) => p.average_quality_score);
  const repsValues = trendPoints.map((p) => p.total_reps);
  const qualityPath = buildPath(qualityValues, 0, 100);
  const repsPath = buildPath(repsValues, 0, Math.max(...repsValues, 1));

  return (
    <div className="px-6 lg:px-12 py-16 max-w-5xl mx-auto w-full animate-fade-in space-y-8">
      <div>
        <h1 className="text-4xl font-extrabold text-[var(--pke-text-primary)] mb-3 tracking-tight uppercase">
          My Progress
        </h1>
        <p className="text-sm text-[var(--pke-text-secondary)]">
          Tracking rep volume and quality for {user.username}.
        </p>
      </div>

      <div className="bg-[var(--pke-bg-card)] p-6 border border-[var(--pke-border)] rounded-2xl shadow-[var(--pke-shadow-md)] space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-widest text-[var(--pke-text-muted)] font-bold">Exercise</span>
            <select
              value={selectedExercise}
              onChange={(e) => setSelectedExercise(e.target.value)}
              className="rounded-xl px-4 py-2 bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] text-[var(--pke-text-primary)]"
            >
              {EXERCISES.map((ex) => (
                <option key={ex.slug} value={ex.slug}>{ex.displayName}</option>
              ))}
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-widest text-[var(--pke-text-muted)] font-bold">Reps</span>
            <input
              type="number"
              min={0}
              value={repsCompleted}
              onChange={(e) => setRepsCompleted(Number(e.target.value))}
              className="w-28 rounded-xl px-4 py-2 bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] text-[var(--pke-text-primary)]"
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-widest text-[var(--pke-text-muted)] font-bold">Quality (0-100)</span>
            <input
              type="number"
              min={0}
              max={100}
              value={qualityScore}
              onChange={(e) => setQualityScore(Number(e.target.value))}
              className="w-36 rounded-xl px-4 py-2 bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] text-[var(--pke-text-primary)]"
            />
          </label>

          <button onClick={handleLogCheckin} className="pke-btn pke-btn-primary">
            Log Check-In
          </button>
        </div>
        {status && <p className="text-sm text-[var(--pke-text-secondary)]">{status}</p>}
        {error && <p className="text-sm text-[var(--pke-danger)]">{error}</p>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="pke-card p-5">
          <p className="text-xs text-[var(--pke-text-muted)] uppercase tracking-widest font-bold">Total Reps (30d)</p>
          <p className="text-3xl font-extrabold mt-2">{summary?.total_reps ?? 0}</p>
        </div>
        <div className="pke-card p-5">
          <p className="text-xs text-[var(--pke-text-muted)] uppercase tracking-widest font-bold">Avg Quality</p>
          <p className="text-3xl font-extrabold mt-2">{(summary?.average_quality_score ?? 0).toFixed(1)}</p>
        </div>
        <div className="pke-card p-5">
          <p className="text-xs text-[var(--pke-text-muted)] uppercase tracking-widest font-bold">Check-Ins</p>
          <p className="text-3xl font-extrabold mt-2">{summary?.total_checkins ?? 0}</p>
        </div>
      </div>

      <div className="bg-[var(--pke-bg-card)] p-6 border border-[var(--pke-border)] rounded-2xl shadow-[var(--pke-shadow-md)]">
        <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--pke-text-muted)] mb-4">Daily Trend</h2>
        {loading ? (
          <p className="text-sm text-[var(--pke-text-secondary)]">Loading trend...</p>
        ) : hasTrend ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] p-4">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--pke-text-muted)] mb-3">
                Rep Quality by Date
              </p>
              <div className="h-44 w-full">
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
                  <line x1="0" y1="100" x2="100" y2="100" stroke="var(--pke-border)" strokeWidth="0.7" />
                  <line x1="0" y1="0" x2="0" y2="100" stroke="var(--pke-border)" strokeWidth="0.7" />
                  <path d={qualityPath} fill="none" stroke="#7c3aed" strokeWidth="2.2" />
                </svg>
              </div>
              <div className="flex justify-between text-[10px] text-[var(--pke-text-muted)] mt-2">
                <span>{trendPoints[0]?.date ?? ""}</span>
                <span>{trendPoints[trendPoints.length - 1]?.date ?? ""}</span>
              </div>
              <p className="text-[10px] text-[var(--pke-text-muted)] mt-1">Y axis: quality score</p>
            </div>

            <div className="rounded-xl bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] p-4">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--pke-text-muted)] mb-3">
                Rep Quantity by Date
              </p>
              <div className="h-44 w-full">
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
                  <line x1="0" y1="100" x2="100" y2="100" stroke="var(--pke-border)" strokeWidth="0.7" />
                  <line x1="0" y1="0" x2="0" y2="100" stroke="var(--pke-border)" strokeWidth="0.7" />
                  <path d={repsPath} fill="none" stroke="#10b981" strokeWidth="2.2" />
                </svg>
              </div>
              <div className="flex justify-between text-[10px] text-[var(--pke-text-muted)] mt-2">
                <span>{trendPoints[0]?.date ?? ""}</span>
                <span>{trendPoints[trendPoints.length - 1]?.date ?? ""}</span>
              </div>
              <p className="text-[10px] text-[var(--pke-text-muted)] mt-1">Y axis: total reps</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-[var(--pke-text-secondary)]">No check-ins yet for this exercise.</p>
        )}
      </div>
    </div>
  );
}
