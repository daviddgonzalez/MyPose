
const PIPELINE_STEPS = [
  { step: "1", title: "Capture", description: "Webcam or video upload" },
  { step: "2", title: "Extract", description: "MediaPipe pose landmarks" },
  { step: "3", title: "Normalize", description: "Scale & alignment" },
  { step: "4", title: "Evaluate", description: "Neural network analysis" },
];

export default function Home() {
  return (
    <div className="h-[calc(100vh-67px)] overflow-hidden flex flex-col justify-center px-6 lg:px-12 w-full max-w-7xl mx-auto relative">

      {/* Decorative gradient orbs */}
      <div className="hero-orb hero-orb-1" />
      <div className="hero-orb hero-orb-2" />
      <div className="hero-orb hero-orb-3" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center h-full w-full justify-items-center relative z-10">

        {/* Left: Hero Text */}
        <div className="space-y-6 animate-slide-up flex flex-col items-center lg:items-start text-center lg:text-left">


          <h1 className="text-6xl sm:text-8xl font-extrabold tracking-tighter leading-[0.9]">
            <span className="gradient-text">My</span>
            <span className="text-[var(--pke-text-primary)]">Pose</span>
          </h1>

          <p className="text-lg text-[var(--pke-text-secondary)] leading-relaxed max-w-lg">
            Movement analysis that learns <em className="not-italic font-semibold text-[var(--pke-text-primary)]">your body</em>.
            Calibrate once, then get real-time form feedback personalized to
            your unique biomechanics.
          </p>

          {/* Quick stats */}
          <div className="flex items-center gap-6 pt-2">
            <div className="text-center">
              <p className="text-2xl font-extrabold gradient-text">7</p>
              <p className="text-[11px] text-[var(--pke-text-muted)] uppercase tracking-widest font-semibold">Exercises</p>
            </div>
            <div className="w-px h-8 bg-[var(--pke-border)]" />
            <div className="text-center">
              <p className="text-2xl font-extrabold gradient-text">33</p>
              <p className="text-[11px] text-[var(--pke-text-muted)] uppercase tracking-widest font-semibold">Landmarks</p>
            </div>
            <div className="w-px h-8 bg-[var(--pke-border)]" />
            <div className="text-center">
              <p className="text-2xl font-extrabold gradient-text">Live</p>
              <p className="text-[11px] text-[var(--pke-text-muted)] uppercase tracking-widest font-semibold">Feedback</p>
            </div>
          </div>
        </div>

        {/* Right: How It Works Card */}
        <div className="animate-scale-in flex justify-center w-full stagger-2">
          <div className="bg-[var(--pke-bg-card)] p-8 lg:p-10 relative overflow-hidden w-full border border-[var(--pke-border)] rounded-2xl shadow-[var(--pke-shadow-md)] hover:shadow-[var(--pke-shadow-xl)] transition-all duration-500 group">

            {/* Gradient top accent */}
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-[#ff6154] via-[#ff8a65] to-[#7c3aed] opacity-80 group-hover:opacity-100 transition-opacity" />

            <h2 className="text-xs font-extrabold text-[var(--pke-text-muted)] mb-8 uppercase tracking-[0.2em]">
              How It Works
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-8 relative z-10">
              {PIPELINE_STEPS.map((item, i) => (
                <div key={item.step} className={`animate-fade-in stagger-${i + 1} group/step`}>
                  <div className="flex items-center gap-4 mb-2">
                    <span className="w-10 h-10 bg-gradient-to-br from-[#ff615418] to-[#7c3aed15] text-sm font-extrabold text-[var(--pke-accent)] flex items-center justify-center rounded-xl shadow-sm border border-[var(--pke-border)] group-hover/step:shadow-[var(--pke-shadow-glow)] group-hover/step:border-[var(--pke-accent)] transition-all duration-300">
                      {item.step}
                    </span>
                    <div>
                      <h3 className="text-sm font-bold text-[var(--pke-text-primary)] uppercase tracking-wide">
                        {item.title}
                      </h3>
                      <p className="text-xs text-[var(--pke-text-muted)]">
                        {item.description}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
