import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { roleLine } from "@/lib/people"
import type { Degree, Person } from "@/lib/types"
import { cn } from "@/lib/utils"

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("")

function hue(s: string) {
  let h = 0
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360
  return h
}

export function PersonAvatar({ name, className }: { name: string; className?: string }) {
  const h = hue(name)
  return (
    <Avatar className={cn("size-8", className)}>
      <AvatarFallback
        className="text-[11px] font-semibold"
        style={{ background: `oklch(0.93 0.03 ${h} / 0.9)`, color: `oklch(0.38 0.06 ${h})` }}
      >
        {initials(name)}
      </AvatarFallback>
    </Avatar>
  )
}

export function PersonCell({ person, className, size = "md" }: { person: Pick<Person, "name" | "title" | "company">; className?: string; size?: "sm" | "md" }) {
  return (
    <div className={cn("flex min-w-0 items-center gap-3", className)}>
      <PersonAvatar name={person.name} className={size === "sm" ? "size-7" : undefined} />
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{person.name}</div>
        {roleLine(person) && <div className="text-muted-foreground truncate text-xs">{roleLine(person)}</div>}
      </div>
    </div>
  )
}

const DEGREE_TEXT = { 1: "1st", 2: "2nd", 3: "3rd" } as const

export function DegreeBadge({ degree, className }: { degree: Degree | null | undefined; className?: string }) {
  return (
    <Badge variant="outline" className={cn("text-muted-foreground gap-1.5 font-medium", className)}>
      <span
        className={cn(
          "size-1.5 rounded-full",
          degree === 1 ? "bg-primary" : degree === 2 ? "bg-foreground/50" : degree === 3 ? "bg-foreground/25" : "border-foreground/30 border"
        )}
      />
      {degree ? DEGREE_TEXT[degree] : "Out of network"}
    </Badge>
  )
}
