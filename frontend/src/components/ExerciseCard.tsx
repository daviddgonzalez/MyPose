"use client";

import Link from "next/link";
import type { Exercise } from "@/lib/types";

interface ExerciseCardProps {
  exercise: Exercise;
  index?: number;
}

export default function ExerciseCard({ exercise, index = 0 }: ExerciseCardProps) {
  return (
    <Link
      href={`/catalog/${exercise.slug}`}
      className={`group block animate-scale-in stagger-${index + 1}`}
      id={`exercise-card-${exercise.slug}`}
    >
      <div className="pke-card pke-card-interactive p-6 relative overflow-hidden h-full">
        {/* Colored top accent bar */}
        <div
          className="absolute top-0 left-0 right-0 h-1 transition-all duration-500 group-hover:h-1.5"
          style={{
            background: `linear-gradient(90deg, ${exercise.color}, ${exercise.color}88)`,
          }}
        />

        {/* Header */}
        <div className="flex items-start justify-between mb-4 mt-1">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl transition-all duration-300 group-hover:scale-110 group-hover:shadow-lg"
            style={{
              background: `linear-gradient(135deg, ${exercise.color}18, ${exercise.color}08)`,
              boxShadow: `0 0 0 1px ${exercise.color}15`,
            }}
          >
            {exercise.icon}
          </div>
          <span
            className={`pke-badge ${
              exercise.difficulty === "Beginner"
                ? "pke-badge-success"
                : exercise.difficulty === "Intermediate"
                ? "pke-badge-warning"
                : "pke-badge-danger"
            }`}
          >
            {exercise.difficulty}
          </span>
        </div>

        {/* Content */}
        <h3 className="text-base font-bold text-[var(--pke-text-primary)] mb-2 group-hover:text-[var(--pke-accent)] transition-colors">
          {exercise.displayName}
        </h3>
        <p className="text-sm text-[var(--pke-text-secondary)] leading-relaxed line-clamp-2 mb-5">
          {exercise.description}
        </p>

        {/* Target Joints */}
        <div className="flex flex-wrap gap-1.5">
          {exercise.targetJoints.slice(0, 3).map((joint) => (
            <span
              key={joint}
              className="text-[11px] px-2.5 py-1 rounded-full bg-[var(--pke-bg-surface)] text-[var(--pke-text-muted)] border border-[var(--pke-border)] font-medium"
            >
              {joint.replace(/_/g, " ")}
            </span>
          ))}
          {exercise.targetJoints.length > 3 && (
            <span className="text-[11px] px-2.5 py-1 rounded-full text-[var(--pke-text-muted)] font-medium">
              +{exercise.targetJoints.length - 3} more
            </span>
          )}
        </div>

        {/* Hover Arrow — slides in */}
        <div className="mt-5 flex items-center gap-1.5 text-xs text-[var(--pke-accent)] font-semibold opacity-0 translate-x-[-8px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300">
          <span>View details</span>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" /></svg>
        </div>
      </div>
    </Link>
  );
}
