import { useMemo } from "react"

import type { Route } from "@/lib/routes"
import type { PathEdge, Person } from "@/lib/types"
import { cn } from "@/lib/utils"

/** All shortest paths as a layered diagram (one column per hop), with the best route highlighted. */
export function PathMap({ edges, me, target, best, people }: { edges: PathEdge[]; me: string; target: string; best?: Route; people: Map<string, Person> }) {
  const layout = useMemo(() => {
    const cols = new Map<number, string[]>([[0, [me]]])
    for (const e of edges) {
      for (const [id, h] of [[e.a, e.hop], [e.b, e.hop + 1]] as const) {
        if (!cols.has(h)) cols.set(h, [])
        if (!cols.get(h)!.includes(id)) cols.get(h)!.push(id)
      }
    }
    const maxRows = Math.min(8, Math.max(...[...cols.values()].map((c) => c.length)))
    const W = 320
    const rowH = 40
    const H = Math.max(110, maxRows * rowH + 30)
    const nCols = cols.size
    const pos = new Map<string, { x: number; y: number }>()
    for (const [h, ids] of cols) {
      const shown = ids.slice(0, 8)
      shown.forEach((id, i) => pos.set(id, { x: 36 + (h * (W - 72)) / Math.max(1, nCols - 1), y: H / 2 + (i - (shown.length - 1) / 2) * rowH }))
    }
    return { pos, W, H, lastX: 36 + (W - 72), hidden: [...cols.values()].reduce((n, c) => n + Math.max(0, c.length - 8), 0) }
  }, [edges, me])

  const onBest = (a: string, b: string) => {
    if (!best) return false
    const i = best.path.indexOf(a)
    return i >= 0 && best.path[i + 1] === b
  }

  return (
    <div>
      <svg viewBox={`0 0 ${layout.W} ${layout.H}`} className="w-full" role="img" aria-label="All shortest paths">
        {edges.map((e) => {
          const a = layout.pos.get(e.a)
          const b = layout.pos.get(e.b)
          if (!a || !b) return null
          const mid = (a.x + b.x) / 2
          const on = onBest(e.a, e.b)
          return (
            <path
              key={`${e.a}-${e.b}`}
              d={`M${a.x},${a.y} C${mid},${a.y} ${mid},${b.y} ${b.x},${b.y}`}
              className={cn("fill-none", on ? "stroke-primary" : "stroke-foreground/15")}
              strokeWidth={on ? 2 : 1}
            />
          )
        })}
        {[...layout.pos].map(([id, { x, y }]) => {
          const on = best?.path.includes(id)
          const label = id === me ? "You" : (people.get(id)?.name ?? "")
          return (
            <g key={id}>
              <circle cx={x} cy={y} r={id === me || id === target ? 6 : 4.5} className={cn(id === me ? "fill-primary" : id === target ? "fill-foreground" : on ? "fill-primary/80" : "fill-foreground/35")} />
              <text
                x={x}
                y={y - 9}
                textAnchor={x <= 36 ? "start" : x >= layout.lastX ? "end" : "middle"}
                dx={x <= 36 ? -6 : x >= layout.lastX ? 6 : 0}
                className={cn("stroke-card text-[11px]", on ? "fill-foreground font-medium" : "fill-muted-foreground")}
                strokeWidth={3}
                paintOrder="stroke"
              >
                {label.length > 16 ? label.slice(0, 15) + "…" : label}
              </text>
            </g>
          )
        })}
      </svg>
      {layout.hidden > 0 && <p className="text-muted-foreground mt-1 text-center text-xs">+{layout.hidden} more people on equally short paths</p>}
    </div>
  )
}
