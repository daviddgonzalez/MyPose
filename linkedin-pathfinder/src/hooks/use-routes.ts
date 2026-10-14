import { useApp } from "@/app-context"
import { useAsync } from "@/hooks/use-async"
import { rankRoutes } from "@/lib/routes"
import type { Person } from "@/lib/types"

/** Load the shortest-path graph to `targetId`, the people on it, and the ranked routes. */
export function useRoutesTo(targetId: string | undefined, me: string) {
  const { api } = useApp()
  return useAsync(async () => {
    if (!targetId) return null
    const edges = await api.pathGraph(targetId)
    const ids = [...new Set([targetId, ...edges.flatMap((e) => [e.a, e.b])])]
    const people = new Map<string, Person>((await api.getPeople(ids)).map((p) => [p.id, p]))
    return { edges, people, routes: rankRoutes(edges, me, targetId), target: people.get(targetId) ?? null }
  }, [api, targetId, me])
}
