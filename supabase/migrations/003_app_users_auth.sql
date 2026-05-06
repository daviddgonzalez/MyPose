-- ============================================================
-- PKE — Basic Username/Password Auth (MVP)
-- ============================================================
-- NOTE: This is an app-level auth table for local MVP flow.
-- Passwords are stored as salted PBKDF2 hashes generated in backend code.

CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;

-- Service-role backend access only for now.
CREATE POLICY "No direct reads by anon/authenticated users"
    ON app_users FOR SELECT
    USING (false);

CREATE POLICY "No direct writes by anon/authenticated users"
    ON app_users FOR INSERT
    WITH CHECK (false);
