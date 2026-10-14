import { Link } from "react-router-dom"
import { MoreHorizontal, Plus, Target, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { AddTargetDialog } from "@/components/add-target-dialog"
import { useLayout } from "@/components/app-layout"
import { EmptyState, PageHeader } from "@/components/page"
import { DegreeBadge, PersonCell } from "@/components/person"
import { RouteChain } from "@/components/route-chain"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useTargets } from "@/hooks/use-targets"
import type { Degree } from "@/lib/types"

const ago = (iso: string) => {
  const d = Math.round((Date.now() - new Date(iso).getTime()) / 864e5)
  return d <= 0 ? "Today" : d === 1 ? "Yesterday" : `${d}d ago`
}

export function TargetsPage() {
  const { api } = useApp()
  const { profile } = useLayout()
  const targets = useTargets(profile.person_id!)

  const remove = async (id: string, name: string) => {
    await api.removeTarget(id)
    toast(`Removed ${name}`)
    targets.reload()
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Targets"
        description="People you want to reach, with the warmest route to each."
        actions={
          <AddTargetDialog onAdded={targets.reload}>
            <Button>
              <Plus /> Add target
            </Button>
          </AddTargetDialog>
        }
      />
      {targets.loading && !targets.data ? (
        <div className="grid gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : !targets.data?.length ? (
        <EmptyState icon={<Target />} title="No targets yet" description="Add someone you'd like an intro to. You can search everyone in the shared network." />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Person</TableHead>
                <TableHead>Best route</TableHead>
                <TableHead>Degree</TableHead>
                <TableHead className="hidden lg:table-cell">Note</TableHead>
                <TableHead className="hidden md:table-cell">Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {targets.data.map((t) => (
                <TableRow key={t.person.id}>
                  <TableCell className="pl-4">
                    <Link to={`/app/path/${t.person.id}`} className="block max-w-56">
                      <PersonCell person={t.person} />
                    </Link>
                  </TableCell>
                  <TableCell>
                    {t.best ? (
                      <Link to={`/app/path/${t.person.id}`} className="flex items-center gap-2">
                        <RouteChain route={{ ...t.best, path: t.best.path.slice(0, -1) }} people={t.people} compact />
                        {t.routeCount > 1 && <span className="text-muted-foreground text-xs">+{t.routeCount - 1}</span>}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-sm">No route yet</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <DegreeBadge degree={t.best ? (Math.min(t.best.hops, 3) as Degree) : null} />
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden max-w-56 truncate lg:table-cell">{t.note}</TableCell>
                  <TableCell className="text-muted-foreground hidden md:table-cell">{ago(t.created_at)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label="Actions">
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem variant="destructive" onSelect={() => remove(t.person.id, t.person.name)}>
                          <Trash2 /> Remove target
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
