import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <rect width="24" height="24" rx="6" className="fill-foreground" />
        <path d="M6.5 16.5 L11 8 L17.5 12" className="stroke-background" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        <circle cx="6.5" cy="16.5" r="2" className="fill-background" />
        <circle cx="11" cy="8" r="2" className="fill-background" />
        <circle cx="17.5" cy="12" r="2.2" className="fill-primary" />
      </svg>
      <span>Pathfinder</span>
    </span>
  )
}
