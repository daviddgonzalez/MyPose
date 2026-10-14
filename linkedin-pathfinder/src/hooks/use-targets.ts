import { useApp } from "@/app-context"
import { useAsync } from "@/hooks/use-async"
import { rankRoutes, type Route } from "@/lib/routes"
import type { Person, Target } from "@/lib/types"

export interface TargetSummary extends Target {
  best: Route | null
  routeCount: number
  people: Map<string, Person>
}

/** Targets plus the best route to each. */
export function useTargets(me: string) {
  const { api } = useApp()
  return useAsync(async () => {
    const targets = await api.listTargets()
    const graphs = await Promise.all(targets.map((t) => api.pathGraph(t.person.id)))
    const routes = targets.map((t, i) => rankRoutes(graphs[i], me, t.person.id))
    const ids = [...new Set(routes.flatMap((r) => r[0]?.path ?? []))]
    const people = new Map<string, Person>((await api.getPeople(ids)).map((p) => [p.id, p]))
    return targets.map((t, i): TargetSummary => ({ ...t, best: routes[i][0] ?? null, routeCount: routes[i].length, people }))
  }, [api, me])
}
