import { ChevronRight } from "lucide-react"

import { PersonAvatar } from "@/components/person"
import { STRENGTH_LABEL, type Route } from "@/lib/routes"
import type { Person } from "@/lib/types"
import { cn } from "@/lib/utils"

/** You → first contact → … → target, with relationship strength on each link. */
export function RouteChain({ route, people, compact = false }: { route: Route; people: Map<string, Person>; compact?: boolean }) {
  return (
    <ol className="flex flex-wrap items-center gap-y-2">
      {route.path.map((id, i) => {
        const p = people.get(id)
        const isYou = i === 0
        const isFirst = i === 1 && route.path.length > 2
        const isTarget = i === route.path.length - 1
        return (
          <li key={id} className="flex items-center">
            {i > 0 && (
              <span className="text-muted-foreground mx-1.5 flex flex-col items-center text-[10px] leading-none font-medium tracking-wide uppercase">
                {!compact && <span className="mb-0.5">{STRENGTH_LABEL[route.strengths[i - 1]]}</span>}
                <ChevronRight className="size-3.5" />
              </span>
            )}
            <span
              className={cn(
                "bg-background flex items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-sm",
                compact && "py-0.5 pl-0.5 text-xs",
                isFirst && "border-primary ring-primary/15 ring-4",
                isTarget && "bg-foreground text-background border-foreground"
              )}
            >
              {isYou ? (
                <span className={cn("bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full text-[10px] font-semibold", compact && "size-5")}>
                  You
                </span>
              ) : (
                <PersonAvatar name={p?.name ?? "?"} className={compact ? "size-5" : "size-6"} />
              )}
              <span className="font-medium whitespace-nowrap">{isYou ? "You" : (p?.name ?? "Unknown")}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
