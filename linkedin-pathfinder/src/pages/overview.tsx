import { Link } from "react-router-dom"
import { ArrowRight, Check, ChevronRight, Plus, Search, Target, Upload } from "lucide-react"

import { useApp } from "@/app-context"
import { AddTargetDialog } from "@/components/add-target-dialog"
import { useLayout } from "@/components/app-layout"
import { EmptyState, Kbd, PageHeader } from "@/components/page"
import { DegreeBadge, PersonCell } from "@/components/person"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAsync } from "@/hooks/use-async"
import { useTargets } from "@/hooks/use-targets"
import type { Degree } from "@/lib/types"
import { cn } from "@/lib/utils"

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
}

function Stat({ label, value, hint, loading }: { label: string; value?: number; hint: string; loading: boolean }) {
  return (
    <div className="bg-card rounded-xl border p-4">
      <div className="text-muted-foreground text-xs font-medium">{label}</div>
      {loading ? <Skeleton className="mt-2 h-7 w-16" /> : <div className="mt-1 text-2xl font-semibold tabular-nums">{(value ?? 0).toLocaleString()}</div>}
      <div className="text-muted-foreground mt-1 text-xs">{hint}</div>
    </div>
  )
}

export function OverviewPage() {
  const { api } = useApp()
  const { profile, openSearch } = useLayout()
  const stats = useAsync(() => api.stats(), [api])
  const targets = useTargets(profile.person_id!)
  const s = stats.data

  const checklist = [
    { done: true, label: "Add your LinkedIn profile", to: "/app/settings" },
    { done: (s?.first ?? 0) > 0, label: "Import your connections", to: "/app/import" },
    { done: (s?.targets ?? 0) > 0, label: "Pick someone to reach", to: "/app/targets" },
  ]
  const showChecklist = s && checklist.some((c) => !c.done)

  return (
    <div className="grid gap-8">
      <PageHeader
        title={`${greeting()}, ${profile.full_name?.split(" ")[0] ?? "there"}`}
        description="Here's how far your network reaches today."
        actions={
          <>
            <Button variant="outline" onClick={openSearch}>
              <Search /> Find someone <Kbd className="ml-1">⌘K</Kbd>
            </Button>
            <AddTargetDialog onAdded={targets.reload}>
              <Button>
                <Plus /> Add target
              </Button>
            </AddTargetDialog>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="1st degree" value={s?.first} hint="People you're connected to" loading={stats.loading} />
        <Stat label="2nd degree" value={s?.second} hint="One intro away" loading={stats.loading} />
        <Stat label="3rd degree" value={s?.third} hint="Two intros away" loading={stats.loading} />
        <Stat label="Network members" value={s?.members} hint={`${(s?.people ?? 0).toLocaleString()} people mapped`} loading={stats.loading} />
      </div>

      <div className={cn("grid gap-6", showChecklist && "lg:grid-cols-[1fr_320px]")}>
        <Card className="gap-0 py-0">
          <CardHeader className="border-b py-4">
            <CardTitle className="text-sm">Your targets</CardTitle>
            <CardDescription>The best route to each person you want to reach.</CardDescription>
            <CardAction>
              <Button asChild variant="ghost" size="sm">
                <Link to="/app/targets">
                  View all <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="p-0">
            {targets.loading && !targets.data ? (
              <div className="grid gap-3 p-4">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : targets.data?.length ? (
              <ul className="divide-y">
                {targets.data.slice(0, 6).map((t) => {
                  const first = t.best && t.best.hops > 1 ? t.people.get(t.best.path[1]) : null
                  return (
                    <li key={t.person.id}>
                      <Link to={`/app/path/${t.person.id}`} className="hover:bg-muted/40 flex items-center gap-4 px-6 py-3 transition-colors">
                        <PersonCell person={t.person} className="flex-1" />
                        <div className="text-muted-foreground hidden min-w-0 flex-1 truncate text-sm sm:block">
                          {t.best ? (
                            t.best.hops === 1 ? (
                              "Already connected"
                            ) : (
                              <>
                                via <span className="text-foreground font-medium">{first?.name}</span>
                              </>
                            )
                          ) : (
                            "No route yet"
                          )}
                        </div>
                        <DegreeBadge degree={t.best ? (Math.min(t.best.hops, 3) as Degree) : null} />
                        <ChevronRight className="text-muted-foreground size-4" />
                      </Link>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <EmptyState
                className="m-4"
                icon={<Target />}
                title="No targets yet"
                description="Add someone you want to reach and we'll find the warmest route to them."
                action={
                  <AddTargetDialog onAdded={targets.reload}>
                    <Button size="sm">
                      <Plus /> Add target
                    </Button>
                  </AddTargetDialog>
                }
              />
            )}
          </CardContent>
        </Card>

        {showChecklist && (
          <Card className="h-fit gap-4">
            <CardHeader>
              <CardTitle className="text-sm">Get set up</CardTitle>
              <CardDescription>{checklist.filter((c) => c.done).length} of 3 done</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-1">
              {checklist.map((c) => (
                <Link key={c.label} to={c.to} className="hover:bg-muted/50 flex items-center gap-3 rounded-md p-2 text-sm">
                  <span className={cn("flex size-5 items-center justify-center rounded-full border", c.done && "bg-primary border-primary text-primary-foreground")}>
                    {c.done && <Check className="size-3" />}
                  </span>
                  <span className={cn(c.done && "text-muted-foreground line-through")}>{c.label}</span>
                </Link>
              ))}
              <Button asChild size="sm" variant="outline" className="mt-3">
                <Link to="/app/import">
                  <Upload /> Import connections
                </Link>
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
