"use client";

import { useEffect, useState } from "react";
import CalibrationWizard from "@/components/CalibrationWizard";
import LiveSession from "@/components/LiveSession";
import VideoUploader from "@/components/VideoUploader";
import { getStoredUser, getUserUpdatedEventName } from "@/lib/user";

type Tab = "upload" | "live" | "calibrate";

const TABS: { key: Tab; label: string }[] = [
  { key: "upload", label: "Upload Video" },
  { key: "live", label: "Live Session" },
  { key: "calibrate", label: "Personalize" },
];

export default function ExerciseClient({ exercise }: { exercise: any }) {
  const [activeTab, setActiveTab] = useState<Tab>("upload");
  const [hoverTab, setHoverTab] = useState<Tab | null>(null);
  const [user, setUser] = useState(() => getStoredUser());

  useEffect(() => {
    const sync = () => setUser(getStoredUser());
    window.addEventListener(getUserUpdatedEventName(), sync);
    return () => window.removeEventListener(getUserUpdatedEventName(), sync);
  }, []);

  const currentHighlight = hoverTab || activeTab;

  return (
    <>
      <div className="w-full max-w-[1300px] px-6 xl:px-12 mx-auto mt-2">


        
        {/* Header Section: Title, Difficulty, and Toggle Pill */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-4">
          <div className="flex items-center gap-4 flex-wrap">
            <h1 className="text-3xl lg:text-4xl font-extrabold text-[var(--pke-text-primary)] tracking-tight uppercase">
              {exercise.displayName}
            </h1>
            <span
              className={`px-3 py-1 text-[11px] font-bold uppercase tracking-widest rounded-full ${
                exercise.difficulty === "Beginner"
                  ? "bg-[#10b981]/10 text-[#10b981]"
                  : exercise.difficulty === "Intermediate"
                  ? "bg-[#f59e0b]/10 text-[#f59e0b]"
                  : "bg-[#ef4444]/10 text-[#ef4444]"
              }`}
            >
              {exercise.difficulty}
            </span>
          </div>

          {/* Pill Toggle Button */}
          <div
            className="flex items-center bg-[var(--pke-bg-surface)] rounded-full p-1 border border-[var(--pke-border)] relative shrink-0 shadow-sm"
            onMouseLeave={() => setHoverTab(null)}
          >
            <div
              className="absolute top-1 bottom-1 bg-white rounded-full shadow-md border border-[var(--pke-border)] transition-all duration-300 ease-out"
              style={{
                width: '8rem',
                left: `calc(4px + ${TABS.findIndex((t) => t.key === currentHighlight)} * 8rem)`,
              }}
            />
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                onMouseEnter={() => setHoverTab(t.key)}
                className={`relative z-10 px-5 py-2 text-[10px] font-bold uppercase tracking-widest transition-colors w-32 rounded-full ${activeTab === t.key ? 'text-[var(--pke-text-primary)]' : 'text-[var(--pke-text-muted)]'}`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Description */}
        <p className="text-sm lg:text-base text-[var(--pke-text-secondary)] leading-relaxed max-w-full mb-4">
          Stream your movements in real-time for instant feedback using expert demonstrations.
        </p>

        {/* Joint Pills */}
        <div className="flex flex-wrap gap-x-3 gap-y-2 mb-3 items-center justify-start max-w-full mt-1">
          <span className="text-[10px] font-extrabold text-[var(--pke-text-muted)] uppercase tracking-widest mr-2">
            Target Joints:
          </span>
          {exercise.targetJoints.map((joint: string, idx: number) => (
            <span
              key={joint}
              className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest bg-white border border-[var(--pke-border)] text-[var(--pke-text-primary)] rounded-full shadow-sm hover:border-[var(--pke-border-hover)] transition-colors ${idx % 2 !== 0 ? 'ml-1' : ''}`}
            >
              {joint.replace(/_/g, " ")}
            </span>
          ))}
        </div>

        {/* Target Muscles Pills */}
        <div className="flex flex-wrap gap-x-3 gap-y-2 mb-6 items-center justify-start max-w-full">
          <span className="text-[10px] font-extrabold text-[var(--pke-text-muted)] uppercase tracking-widest mr-2">
            Target Muscles:
          </span>
          {exercise.targetMuscles.map((muscle: string, idx: number) => (
            <span
              key={muscle}
              className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest bg-white border border-[var(--pke-border)] text-[var(--pke-text-primary)] rounded-full shadow-sm hover:border-[var(--pke-border-hover)] transition-colors ${idx % 2 !== 0 ? 'ml-1' : ''}`}
            >
              {muscle}
            </span>
          ))}
        </div>

        {/* Media Window */}
        <div className="w-full">
          {activeTab === "upload" && (
            <VideoUploader userId={user?.userId} exerciseSlug={exercise.slug} />
          )}
          {activeTab === "live" && (
            <LiveSession exerciseName={exercise.slug} userId={user?.userId} />
          )}
          {activeTab === "calibrate" && (
            <CalibrationWizard preselectedExercise={exercise.slug} />
          )}
        </div>
      </div>
    </>
  );
}
