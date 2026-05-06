"use client";

import Link from "next/link";
import { useState, useRef, useEffect } from "react";
import { EXERCISES } from "@/lib/exercises";
import { clearStoredUser, getStoredUser, getUserUpdatedEventName } from "@/lib/user";

export default function Navbar() {
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [activeUsername, setActiveUsername] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const catalogRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (catalogRef.current && !catalogRef.current.contains(event.target as Node)) {
        setCatalogOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const syncUser = () => {
      const user = getStoredUser();
      setActiveUsername(user?.username || null);
    };
    syncUser();
    window.addEventListener("storage", syncUser);
    window.addEventListener(getUserUpdatedEventName(), syncUser);
    return () => {
      window.removeEventListener("storage", syncUser);
      window.removeEventListener(getUserUpdatedEventName(), syncUser);
    };
  }, []);

  return (
    <header className="sticky top-0 w-full z-50 pke-glass h-16 flex items-center px-6 lg:px-12 flex-shrink-0">
      <Link href="/" className="flex items-center mr-10 group">
        <span className="text-xl font-extrabold tracking-tight">
          <span className="gradient-text">My</span>
          <span className="text-[var(--pke-text-primary)]">Pose</span>
        </span>

      </Link>

      <nav className="hidden md:flex items-center gap-1 text-sm font-semibold">
        <Link href="/" className="shimmer-nav px-4 py-2 text-[var(--pke-text-secondary)] hover:text-[var(--pke-text-primary)] rounded-lg hover:bg-[var(--pke-bg-surface)] transition-all">
          Home
        </Link>
        
        <div className="relative" ref={catalogRef}>
          <button 
            onClick={() => setCatalogOpen(!catalogOpen)}
            className="shimmer-nav px-4 py-2 text-[var(--pke-text-secondary)] hover:text-[var(--pke-text-primary)] rounded-lg hover:bg-[var(--pke-bg-surface)] transition-all flex items-center gap-1.5 cursor-pointer font-semibold"
          >
            Exercises
            <svg className={`w-3.5 h-3.5 transition-transform duration-300 ${catalogOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          
          {catalogOpen && (
            <div className="absolute top-full left-0 mt-2 w-72 bg-[var(--pke-bg-card)] shadow-[var(--pke-shadow-xl)] flex flex-col z-50 rounded-md border border-[var(--pke-border)] animate-scale-in origin-top-left overflow-hidden">
              {EXERCISES.map((ex, i) => (
                <Link
                  key={ex.slug}
                  href={`/catalog/${ex.slug}`}
                  onClick={() => setCatalogOpen(false)}
                  className={`px-5 py-3 hover:bg-[var(--pke-bg-surface)] text-[var(--pke-text-primary)] text-sm font-medium transition-all text-left flex items-center gap-3 group/item ${i < EXERCISES.length - 1 ? 'border-b border-[var(--pke-border)]' : ''}`}
                >
                  <span className="group-hover/item:translate-x-0.5 transition-transform">
                    {ex.displayName}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>

      </nav>
      
      <div className="ml-auto hidden md:flex items-center" suppressHydrationWarning>
        {!activeUsername ? (
          <Link href="/login" className="pke-btn pke-btn-primary pke-btn-sm">
            Log In
          </Link>
        ) : (
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen((v) => !v)}
              className="shimmer-nav px-3 py-2 text-sm text-[var(--pke-text-secondary)] hover:text-[var(--pke-text-primary)] rounded-lg hover:bg-[var(--pke-bg-surface)] transition-all flex items-center gap-1.5"
            >
              User: {activeUsername}
              <svg className={`w-3.5 h-3.5 transition-transform duration-300 ${userMenuOpen ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
            {userMenuOpen && (
              <div className="absolute right-0 top-full mt-2 w-44 bg-[var(--pke-bg-card)] shadow-[var(--pke-shadow-xl)] flex flex-col z-50 rounded-md border border-[var(--pke-border)] animate-scale-in origin-top-right overflow-hidden">
                <Link
                  href="/build-progress"
                  onClick={() => setUserMenuOpen(false)}
                  className="px-4 py-3 hover:bg-[var(--pke-bg-surface)] text-[var(--pke-text-primary)] text-sm font-medium transition-all"
                >
                  My Progress
                </Link>
                <button
                  onClick={() => {
                    clearStoredUser();
                    setUserMenuOpen(false);
                  }}
                  className="px-4 py-3 hover:bg-[var(--pke-bg-surface)] text-left text-sm font-medium text-[var(--pke-text-primary)] transition-all border-t border-[var(--pke-border)]"
                >
                  Log Out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
