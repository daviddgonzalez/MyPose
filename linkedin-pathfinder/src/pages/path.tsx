import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Bookmark, BookmarkCheck, Copy, ExternalLink, Route as RouteIcon, UserPlus } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { useLayout } from "@/components/app-layout"
import { EmptyState } from "@/components/page"
import { PathMap } from "@/components/path-map"
import { DegreeBadge, PersonAvatar } from "@/components/person"
import { PersonPicker, type PickedPerson } from "@/components/person-picker"
import { RouteChain } from "@/components/route-chain"
import { StrengthSelect } from "@/components/strength-select"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { useAsync } from "@/hooks/use-async"
import { useRoutesTo } from "@/hooks/use-routes"
import { roleLine } from "@/lib/people"
import { introMessage } from "@/lib/routes"
import type { Degree, Strength } from "@/lib/types"

function AddWayIn({ targetId, targetName, onAdded }: { targetId: string; targetName: string; onAdded: () => void }) {
  const { api } = useApp()
  const [who, setWho] = useState<PickedPerson | null>(null)
  const [strength, setStrength] = useState<Strength>(2)
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!who) return
    setBusy(true)
    try {
      const id = who.id ?? (await api.ensurePerson({ name: who.name }))
      await api.addLink(id, targetId, strength)
      toast.success(`Noted: ${who.name} knows ${targetName}`)
      setWho(null)
      onAdded()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="grid gap-3">
      <PersonPicker value={who} onChange={setWho} placeholder={`Who knows ${targetName.split(" ")[0]}?`} />
      <div className="flex gap-2">
        <StrengthSelect value={strength} onChange={setStrength} className="flex-1" />
        <Button onClick={save} disabled={!who || busy}>
          Add
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">Only you see links you add here. Use mutual connections from their LinkedIn profile, coworkers, classmates, and so on.</p>
    </div>
  )
}

export function PathPage() {
  const { id } = useParams()
  const { api } = useApp()
  const { profile } = useLayout()
  const me = profile.person_id!
  const data = useRoutesTo(id, me)
  const targets = useAsync(() => api.listTargets(), [api, id])
  const [edited, setEdited] = useState<{ key: string; text: string } | null>(null)

  const best = data.data?.routes[0]
  const routeKey = best?.path.join(">") ?? ""
  const message = edited?.key === routeKey ? edited.text : best && data.data ? introMessage(best, data.data.people) : ""
  const setMessage = (text: string) => setEdited({ key: routeKey, text })

  if (data.loading && !data.data) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-16 w-80" />
        <Skeleton className="h-48" />
      </div>
    )
  }
  const d = data.data
  const target = d?.target
  if (!d || !target) return <EmptyState icon={<RouteIcon />} title="Person not found" description="They may have been removed from the network." />

  const isTarget = targets.data?.some((t) => t.person.id === target.id)
  const toggleTarget = async () => {
    if (isTarget) await api.removeTarget(target.id)
    else await api.addTarget(target.id)
    toast.success(isTarget ? "Removed from targets" : "Saved to targets")
    targets.reload()
  }
  const first = best && best.hops > 1 ? d.people.get(best.path[1]) : null
  const next = best && best.hops > 1 ? d.people.get(best.path[2]) : null

  return (
    <div className="grid gap-6">
      <Link to="/app/targets" className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-sm">
        <ArrowLeft className="size-4" /> Targets
      </Link>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <PersonAvatar name={target.name} className="size-12 text-base" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{target.name}</h1>
            <DegreeBadge degree={best ? (Math.min(best.hops, 3) as Degree) : null} />
          </div>
          {roleLine(target) && <p className="text-muted-foreground text-sm">{roleLine(target)}</p>}
        </div>
        <div className="flex gap-2">
          {target.linkedin_url && (
            <Button variant="outline" asChild>
              <a href={target.linkedin_url} target="_blank" rel="noreferrer">
                <ExternalLink /> LinkedIn
              </a>
            </Button>
          )}
          <Button variant={isTarget ? "outline" : "default"} onClick={toggleTarget}>
            {isTarget ? <BookmarkCheck /> : <Bookmark />} {isTarget ? "Saved" : "Save as target"}
          </Button>
        </div>
      </div>

      {!best ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          <EmptyState
            icon={<RouteIcon />}
            title="No route yet"
            description={`Nobody in the network has ${target.name.split(" ")[0]} within four hops of you. Add someone who knows them, or invite friends to upload their connections. Every upload extends everyone's reach.`}
          />
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Know a way in?</CardTitle>
            </CardHeader>
            <CardContent>
              <AddWayIn targetId={target.id} targetName={target.name} onAdded={data.reload} />
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          <div className="grid min-w-0 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Recommended route</CardTitle>
                <CardDescription>
                  {best.hops === 1 ? "You're directly connected." : `${best.hops} hops. Shortest path, warmest relationships first.`}
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-5">
                <div className="overflow-x-auto pb-1">
                  <RouteChain route={best} people={d.people} />
                </div>
                <div className="bg-brand-soft/60 border-primary/15 rounded-lg border p-4 text-sm">
                  {first ? (
                    <>
                      <div className="text-primary mb-1 text-xs font-semibold tracking-wide uppercase">Next step</div>
                      Message <span className="font-semibold">{first.name}</span> and ask them to introduce you to{" "}
                      <span className="font-semibold">{next?.name}</span>.
                    </>
                  ) : (
                    <>You're already connected to {target.name}. Message them directly.</>
                  )}
                </div>
                {first && (
                  <div className="grid gap-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Intro request</span>
                      <div className="flex gap-1">
                        {first.linkedin_url && (
                          <Button variant="ghost" size="sm" asChild>
                            <a href={first.linkedin_url} target="_blank" rel="noreferrer">
                              <ExternalLink /> Open {first.name.split(" ")[0]}'s profile
                            </a>
                          </Button>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(message)
                              toast.success("Copied to clipboard")
                            } catch {
                              toast.error("Couldn't access the clipboard")
                            }
                          }}
                        >
                          <Copy /> Copy
                        </Button>
                      </div>
                    </div>
                    <Textarea value={message} onChange={(e) => setMessage(e.target.value)} className="min-h-28 text-sm" />
                  </div>
                )}
              </CardContent>
            </Card>

            {d.routes.length > 1 && (
              <Card className="gap-0 pb-0">
                <CardHeader className="pb-4">
                  <CardTitle className="text-sm">Other routes</CardTitle>
                  <CardDescription>Through your other connections, ranked by how well everyone knows each other.</CardDescription>
                </CardHeader>
                <ul className="divide-y border-t">
                  {d.routes.slice(1, 8).map((r) => (
                    <li key={r.path.join()} className="overflow-x-auto px-6 py-3">
                      <RouteChain route={r} people={d.people} compact />
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          <div className="grid h-fit gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Path map</CardTitle>
                <CardDescription>Everyone on an equally short path.</CardDescription>
              </CardHeader>
              <CardContent>
                <PathMap edges={d.edges} me={me} target={target.id} best={best} people={d.people} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <UserPlus className="size-4" /> Know another way in?
                </CardTitle>
              </CardHeader>
              <CardContent>
                <AddWayIn targetId={target.id} targetName={target.name} onAdded={data.reload} />
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
