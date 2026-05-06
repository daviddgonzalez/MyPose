"use client";

import Link from "next/link";
import { useState } from "react";
import { loginUser, registerUser } from "@/lib/api";
import { saveStoredUser } from "@/lib/user";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleAuth(mode: "login" | "register") {
    setLoading(true);
    setError(null);
    setStatusMsg("");
    try {
      const payload = { username: username.trim().toLowerCase(), password };
      const res = mode === "register" ? await registerUser(payload) : await loginUser(payload);
      saveStoredUser({ userId: res.user_id, username: res.username });
      setStatusMsg(mode === "register" ? "Account created and logged in." : "Logged in.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="px-6 lg:px-12 py-16 max-w-xl mx-auto w-full animate-fade-in">
      <h1 className="text-4xl font-extrabold text-[var(--pke-text-primary)] tracking-tight uppercase">
        Login
      </h1>
      <p className="text-sm text-[var(--pke-text-secondary)] mt-3 mb-8">
        Use a unique username and password to access your saved data.
      </p>

      <div className="bg-[var(--pke-bg-card)] p-8 border border-[var(--pke-border)] rounded-2xl shadow-[var(--pke-shadow-md)] space-y-5">
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--pke-text-muted)]">
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. dcooper"
              className="w-full rounded-xl px-4 py-3 bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] text-[var(--pke-text-primary)] outline-none focus:border-[var(--pke-accent)]"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--pke-text-muted)]">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="minimum 6 characters"
              className="w-full rounded-xl px-4 py-3 bg-[var(--pke-bg-surface)] border border-[var(--pke-border)] text-[var(--pke-text-primary)] outline-none focus:border-[var(--pke-accent)]"
            />
          </div>
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={() => void handleAuth("login")}
              disabled={loading}
              className="pke-btn pke-btn-primary"
            >
              Log In
            </button>
            <button
              type="button"
              onClick={() => void handleAuth("register")}
              disabled={loading}
              className="pke-btn pke-btn-secondary"
            >
              Register
            </button>
          </div>
        </div>

        {statusMsg && (
          <div className="text-sm text-[var(--pke-text-secondary)]">
            {statusMsg} <Link href="/" className="underline">Go home</Link>
          </div>
        )}
        {error && <p className="text-sm text-[var(--pke-danger)]">{error}</p>}
      </div>
    </div>
  );
}
