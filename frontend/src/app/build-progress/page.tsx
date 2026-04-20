export default function BuildProgress() {
  const steps = [
    "Docker + Backend + Supabase",
    "Extraction + Normalization",
    "C++ Module (DTW + Joint Angles)",
    "ST-GCN Architecture",
    "Calibration + Evaluation Services",
    "Frontend (React/TypeScript)",
    "Live Pipeline (WebSocket)",
    "Pre-training (Fit3D)",
  ];

  return (
    <div className="px-6 lg:px-12 py-16 max-w-4xl mx-auto w-full animate-fade-in">
      <h1 className="text-4xl font-extrabold text-[var(--pke-text-primary)] mb-3 tracking-tight uppercase">
        Build Progress
      </h1>
      <p className="text-sm text-[var(--pke-text-secondary)] mb-10">
        Tracking the development milestones of the MyPose pipeline.
      </p>

      <div className="bg-[var(--pke-bg-card)] p-10 relative border border-[var(--pke-border)] rounded-2xl shadow-[var(--pke-shadow-md)]">
        {/* Gradient top accent */}
        <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-[#ff6154] via-[#ff8a65] to-[#7c3aed] opacity-80" />

        {/* Vertical connecting line */}
        <div className="absolute left-[54px] top-[80px] bottom-[40px] w-[2px] bg-[var(--pke-success)]" />

        <div className="space-y-8 relative z-10">
          {steps.map((label, i) => (
            <div key={i} className={`flex items-start gap-5 animate-fade-in stagger-${Math.min(i + 1, 7)}`}>
              <span
                className="w-10 h-10 border-[2px] flex items-center justify-center text-[10px] font-bold shrink-0 rounded-full bg-[var(--pke-success)] border-[var(--pke-success)] text-white shadow-[0_0_12px_rgba(16,185,129,0.3)]"
              >
                {i + 1}
              </span>
              <div className="pt-2">
                <p className="text-base font-bold uppercase tracking-wider text-[var(--pke-text-muted)] line-through decoration-[2px]">
                  {label}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
