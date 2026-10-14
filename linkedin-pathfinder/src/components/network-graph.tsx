import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation, type SimulationNodeDatum } from "d3-force"

import type { EgoGraph } from "@/lib/types"
import { cn } from "@/lib/utils"

type Node = EgoGraph["nodes"][number] & SimulationNodeDatum
const SIZE = 640
const RADIUS = { 0: 9, 1: 5.5, 2: 3.5 } as const

/** Your ego network: you in the middle, 1st-degree ring, 2nd-degree outer ring. */
export function NetworkGraph({ graph }: { graph: EgoGraph }) {
  const navigate = useNavigate()
  const [hover, setHover] = useState<string | null>(null)

  const { nodes, links, neighbours } = useMemo(() => {
    // Seed each ring evenly so the layout starts balanced around you.
    const ringCount = [0, 0, 0]
    const ringSize = [1, 0, 0]
    for (const n of graph.nodes) ringSize[n.degree] += n.degree ? 1 : 0
    const nodes: Node[] = graph.nodes.map((n) => {
      const i = ringCount[n.degree]++
      const a = (2 * Math.PI * i) / Math.max(1, ringSize[n.degree])
      const r = [0, 150, 270][n.degree]
      // You stay pinned in the middle; the radial force keeps each ring centred on you.
      const pin = n.degree === 0 ? { fx: SIZE / 2, fy: SIZE / 2 } : {}
      return { ...n, ...pin, x: SIZE / 2 + r * Math.cos(a), y: SIZE / 2 + r * Math.sin(a) }
    })
    const links = graph.links.map((l) => ({ ...l }))
    const meId = graph.nodes.find((n) => n.degree === 0)?.id
    forceSimulation(nodes)
      .force(
        "link",
        // Edges to you are implied by the rings; only peer edges should pull people together.
        forceLink<Node, { source: string | Node; target: string | Node }>(links.filter((l) => l.source !== meId && l.target !== meId))
          .id((d) => d.id)
          .strength(0.02)
      )
      .force("charge", forceManyBody().strength(-28).distanceMax(70))
      .force("radial", forceRadial<Node>((d) => [0, 150, 270][d.degree], SIZE / 2, SIZE / 2).strength(0.9))
      .force("collide", forceCollide<Node>((d) => RADIUS[d.degree] + 2))
      .stop()
      .tick(300)
    const neighbours = new Map<string, Set<string>>()
    for (const l of links) {
      const s = (l.source as unknown as Node).id
      const t = (l.target as unknown as Node).id
      if (!neighbours.has(s)) neighbours.set(s, new Set())
      if (!neighbours.has(t)) neighbours.set(t, new Set())
      neighbours.get(s)!.add(t)
      neighbours.get(t)!.add(s)
    }
    return { nodes, links: links as unknown as { source: Node; target: Node }[], neighbours }
  }, [graph])

  const lit = (id: string) => !hover || hover === id || neighbours.get(hover)?.has(id)
  const hovered = nodes.find((n) => n.id === hover)

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="mx-auto block aspect-square w-full max-w-[640px]" role="img" aria-label="Network graph">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={150} className="fill-none stroke-border" strokeDasharray="2 4" />
        <circle cx={SIZE / 2} cy={SIZE / 2} r={270} className="fill-none stroke-border" strokeDasharray="2 4" />
        <g>
          {links.map((l, i) => {
            const on = hover && (l.source.id === hover || l.target.id === hover)
            return (
              <line
                key={i}
                x1={l.source.x}
                y1={l.source.y}
                x2={l.target.x}
                y2={l.target.y}
                className={cn("transition-opacity", on ? "stroke-primary" : "stroke-foreground")}
                strokeOpacity={on ? 0.8 : hover ? 0.03 : 0.08}
                strokeWidth={on ? 1.2 : 0.8}
              />
            )
          })}
        </g>
        <g>
          {nodes.map((n) => (
            <circle
              key={n.id}
              cx={n.x}
              cy={n.y}
              r={RADIUS[n.degree]}
              className={cn(
                "cursor-pointer transition-opacity",
                n.degree === 0 ? "fill-primary" : n.degree === 1 ? "fill-foreground/70" : "fill-foreground/30",
                n.id === hover && "fill-primary"
              )}
              opacity={lit(n.id) ? 1 : 0.2}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => n.degree !== 0 && navigate(`/app/path/${n.id}`)}
            />
          ))}
        </g>
        {hovered && (
          <g pointerEvents="none">
            <text x={hovered.x} y={(hovered.y ?? 0) - 12} textAnchor="middle" className="fill-foreground stroke-background text-[12px] font-medium" strokeWidth={4} paintOrder="stroke">
              {hovered.degree === 0 ? "You" : hovered.name}
            </text>
          </g>
        )}
      </svg>
      <div className="text-muted-foreground mt-2 flex flex-wrap justify-center gap-4 text-xs">
        <span className="flex items-center gap-1.5"><span className="bg-primary size-2 rounded-full" />You</span>
        <span className="flex items-center gap-1.5"><span className="bg-foreground/70 size-2 rounded-full" />1st degree</span>
        <span className="flex items-center gap-1.5"><span className="bg-foreground/30 size-2 rounded-full" />2nd degree</span>
        <span>Hover to highlight · click to find a path</span>
      </div>
    </div>
  )
}
