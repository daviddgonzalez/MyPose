"use client";

import Link from "next/link";
import { useState, useRef, useEffect } from "react";
import { EXERCISES } from "@/lib/exercises";

export default function Navbar() {
  const [catalogOpen, setCatalogOpen] = useState(false);
  const catalogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (catalogRef.current && !catalogRef.current.contains(event.target as Node)) {
        setCatalogOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 w-full z-50 pke-glass h-16 flex items-center px-6 lg:px-12 flex-shrink-0">
      <Link href="/" className="flex items-center mr-10 group">
        <span className="text-xl font-extrabold tracking-tight">
          <span className="gradient-text">My</span>
          <span className="text-[var(--pke-text-primary)]">Pose</span>
        </span>
        <span className="ml-2 w-2 h-2 rounded-full bg-[var(--pke-accent)] opacity-80 group-hover:opacity-100 group-hover:scale-125 transition-all" />
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

        <Link href="/build-progress" className="shimmer-nav px-4 py-2 text-[var(--pke-text-secondary)] hover:text-[var(--pke-text-primary)] rounded-lg hover:bg-[var(--pke-bg-surface)] transition-all">
          Progress
        </Link>
      </nav>
      
      <div className="ml-auto hidden md:flex items-center gap-2 text-[10px] uppercase font-bold text-[var(--pke-text-muted)] tracking-widest" suppressHydrationWarning>
        <div className="relative flex items-center justify-center w-2 h-2">
          <span className="w-1.5 h-1.5 bg-[var(--pke-success)] rounded-full animate-ping absolute opacity-75" />
          <span className="w-1.5 h-1.5 bg-[var(--pke-success)] rounded-full relative z-10" />
        </div>
        <span className="ml-1 text-[var(--pke-text-muted)] transition-colors">API: {(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/^https?:\/\//, '')}</span>
      </div>
    </header>
  );
}
