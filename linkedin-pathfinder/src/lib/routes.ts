import type { PathEdge, Person, Strength } from "./types"

export interface Route {
  /** Person ids from you to the target, inclusive. */
  path: string[]
  /** strengths[i] is the relationship between path[i] and path[i + 1]. */
  strengths: Strength[]
  cost: number
  hops: number
}

/** Closer relationships are cheaper to ask a favour of. */
export const strengthCost = (s: Strength) => ({ 3: 1, 2: 2, 1: 4 })[s]
export const STRENGTH_LABEL: Record<Strength, string> = { 3: "Close", 2: "Knows", 1: "Weak" }

/**
 * Turn the shortest-path DAG into concrete routes, keep the warmest route per first contact,
 * and rank them. All routes have the same (minimum) number of hops.
 */
export function rankRoutes(edges: PathEdge[], me: string, target: string, maxEnumerated = 5000): Route[] {
  const out = new Map<string, { to: string; s: Strength }[]>()
  for (const e of edges) {
    if (!out.has(e.a)) out.set(e.a, [])
    out.get(e.a)!.push({ to: e.b, s: e.strength })
  }
  const bestByFirst = new Map<string, Route>()
  let enumerated = 0
  const walk = (node: string, path: string[], strengths: Strength[], cost: number) => {
    if (enumerated >= maxEnumerated) return
    if (node === target) {
      enumerated++
      const first = path[1]
      const prev = bestByFirst.get(first)
      if (!prev || cost < prev.cost) bestByFirst.set(first, { path: [...path], strengths: [...strengths], cost, hops: path.length - 1 })
      return
    }
    const nexts = [...(out.get(node) ?? [])].sort((x, y) => y.s - x.s)
    for (const { to, s } of nexts) {
      path.push(to)
      strengths.push(s)
      walk(to, path, strengths, cost + strengthCost(s))
      path.pop()
      strengths.pop()
    }
  }
  walk(me, [me], [], 0)
  return [...bestByFirst.values()].sort((a, b) => a.cost - b.cost || a.hops - b.hops)
}

const firstName = (p: Pick<Person, "name">) => p.name.split(" ")[0]

export function introMessage(route: Route, people: Map<string, Person>): string {
  const first = people.get(route.path[1])
  const next = people.get(route.path[2])
  const target = people.get(route.path[route.path.length - 1])
  if (!first || !target) return ""
  const about = [target.title, target.company].filter(Boolean).join(" at ")
  const who = target.name + (about ? ` (${about})` : "")
  if (route.hops <= 1) return `Hi ${firstName(target)}, hope you're doing well! …`
  if (!next || next.id === target.id) {
    return `Hi ${firstName(first)}, hope you're doing well! I'm hoping to connect with ${who} and noticed you two are connected. Would you be comfortable making a quick intro? Happy to send a short blurb you can forward. Thanks!`
  }
  return `Hi ${firstName(first)}, hope you're doing well! I'm trying to reach ${who}. It looks like ${next.name} knows them, and you know ${firstName(next)}. Would you be open to introducing me to ${firstName(next)}? Happy to send a short blurb you can forward. Thanks!`
}
