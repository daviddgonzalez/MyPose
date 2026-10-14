import type { Degree, PathEdge, Strength } from "./types"

/** Undirected adjacency: node -> (neighbour -> strongest known strength). */
export type Adjacency = Map<string, Map<string, Strength>>

export function buildAdjacency(edges: { a: string; b: string; strength: Strength }[]): Adjacency {
  const adj: Adjacency = new Map()
  const add = (x: string, y: string, s: Strength) => {
    let m = adj.get(x)
    if (!m) adj.set(x, (m = new Map()))
    m.set(y, Math.max(m.get(y) ?? 0, s) as Strength)
  }
  for (const e of edges) {
    add(e.a, e.b, e.strength)
    add(e.b, e.a, e.strength)
  }
  return adj
}

/** Degree (1–3) and mutual count for everyone within three hops. Mirrors private.network() in SQL. */
export function degrees(adj: Adjacency, me: string) {
  const out = new Map<string, { degree: Degree; mutuals: number }>()
  let frontier = [me]
  const seen = new Set([me])
  for (let d = 1; d <= 3; d++) {
    const counts = new Map<string, number>()
    for (const u of frontier) for (const v of adj.get(u)?.keys() ?? []) if (!seen.has(v)) counts.set(v, (counts.get(v) ?? 0) + 1)
    for (const [v, c] of counts) {
      seen.add(v)
      out.set(v, { degree: d as Degree, mutuals: d === 1 ? 0 : c })
    }
    frontier = [...counts.keys()]
  }
  return out
}

/** Every edge on a shortest path from `me` to `target`. Mirrors public.path_graph() in SQL. */
export function shortestPathDag(adj: Adjacency, me: string, target: string, maxHops = 4): PathEdge[] {
  if (me === target) return []
  const dist = new Map([[me, 0]])
  let frontier = [me]
  let found: number | undefined
  for (let level = 0; level < Math.min(maxHops, 6) && frontier.length && found === undefined; level++) {
    const next: string[] = []
    for (const u of frontier)
      for (const v of adj.get(u)?.keys() ?? [])
        if (!dist.has(v)) {
          dist.set(v, level + 1)
          next.push(v)
        }
    frontier = next
    found = dist.get(target)
  }
  if (found === undefined) return []
  const keep = new Map([[target, found]])
  for (let lvl = found - 1; lvl >= 0; lvl--)
    for (const [u, d] of dist)
      if (d === lvl && [...(adj.get(u)?.keys() ?? [])].some((v) => keep.get(v) === lvl + 1)) keep.set(u, lvl)
  const edges: PathEdge[] = []
  for (const [u, d] of keep)
    for (const [v, s] of adj.get(u) ?? []) if (keep.get(v) === d + 1) edges.push({ a: u, b: v, strength: s, hop: d })
  return edges
}
