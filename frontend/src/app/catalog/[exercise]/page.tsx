import Link from "next/link";
import { notFound } from "next/navigation";
import { getExerciseBySlug, EXERCISES } from "@/lib/exercises";
import ExerciseClient from "./ExerciseClient";

interface ExerciseDetailPageProps {
  params: Promise<{ exercise: string }>;
}

export async function generateStaticParams() {
  return EXERCISES.map((ex) => ({ exercise: ex.slug }));
}

export async function generateMetadata({ params }: ExerciseDetailPageProps) {
  const { exercise: slug } = await params;
  const exercise = getExerciseBySlug(slug);
  if (!exercise) return { title: "Not Found — MyPose" };
  return {
    title: `${exercise.displayName} — MyPose`,
    description: exercise.description,
  };
}

export default async function ExerciseDetailPage({
  params,
}: ExerciseDetailPageProps) {
  const { exercise: slug } = await params;
  const exercise = getExerciseBySlug(slug);
  if (!exercise) notFound();

  return (
    <div className="space-y-8 py-6 animate-fade-in w-full flex flex-col items-center">
      <nav className="flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-widest text-[var(--pke-text-muted)]">
        <Link href="/" className="hover:text-[var(--pke-text-primary)] transition-colors">
          Home
        </Link>
        <span className="text-[var(--pke-border)]">/</span>
        <span className="text-[var(--pke-text-primary)]">
          {exercise.displayName}
        </span>
      </nav>

      <ExerciseClient exercise={exercise} />
    </div>
  );
}
