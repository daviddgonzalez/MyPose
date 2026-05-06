-- ============================================================
-- PKE — Progress Check-ins (MVP)
-- ============================================================
-- Tracks user workout quality + rep volume over time for trend views.

CREATE TABLE IF NOT EXISTS progress_checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    exercise_id UUID NOT NULL REFERENCES exercises(id),
    reps_completed INT NOT NULL CHECK (reps_completed >= 0),
    average_quality_score FLOAT NOT NULL CHECK (average_quality_score >= 0 AND average_quality_score <= 100),
    passed_reps INT NOT NULL DEFAULT 0 CHECK (passed_reps >= 0),
    failed_reps INT NOT NULL DEFAULT 0 CHECK (failed_reps >= 0),
    duration_seconds FLOAT,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE progress_checkins ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own progress checkins"
    ON progress_checkins FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own progress checkins"
    ON progress_checkins FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_progress_checkins_user_exercise_created
    ON progress_checkins(user_id, exercise_id, created_at DESC);
