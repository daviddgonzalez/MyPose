import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { ChevronLeft, ChevronRight, Network as NetworkIcon, Route, Search, Table2, Waypoints } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { NetworkGraph } from "@/components/network-graph"
import { EmptyState, PageHeader } from "@/components/page"
import { DegreeBadge, PersonCell } from "@/components/person"
import { StrengthSelect } from "@/components/strength-select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAsync } from "@/hooks/use-async"
import { cn } from "@/lib/utils"

const PAGE = 50
const DEGREES = [
  { value: null, label: "All" },
  { value: 1, label: "1st" },
  { value: 2, label: "2nd" },
  { value: 3, label: "3rd" },
] as const

function useDebounced<T>(value: T, ms = 200) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function NetworkTable() {
  const { api } = useApp()
  const [query, setQuery] = useState("")
  const [degree, setDegree] = useState<1 | 2 | 3 | null>(null)
  const [page, setPage] = useState(0)
  const q = useDebounced(query)
  const res = useAsync(() => api.searchNetwork({ query: q, degree, limit: PAGE, offset: page * PAGE }), [api, q, degree, page])
  const rows = res.data?.rows ?? []
  const total = res.data?.total ?? 0

  return (
    <div className="grid gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input value={query} onChange={(e) => (setQuery(e.target.value), setPage(0))} placeholder="Search by name or company — includes people outside your network" className="pl-8" />
        </div>
        <div className="bg-muted flex w-fit rounded-md p-0.5">
          {DEGREES.map((d) => (
            <button
              key={d.label}
              onClick={() => (setDegree(d.value), setPage(0))}
              className={cn("rounded px-3 py-1 text-sm transition-colors", degree === d.value ? "bg-background font-medium shadow-xs" : "text-muted-foreground hover:text-foreground")}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Name</TableHead>
              <TableHead className="hidden md:table-cell">Company</TableHead>
              <TableHead>Degree</TableHead>
              <TableHead className="hidden sm:table-cell">Mutuals</TableHead>
              <TableHead className="hidden lg:table-cell">Closeness</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {res.loading && !res.data
              ? Array.from({ length: 6 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6} className="pl-4">
                      <Skeleton className="h-8" />
                    </TableCell>
                  </TableRow>
                ))
              : rows.map((p) => (
                  <TableRow key={p.id} className="group">
                    <TableCell className="max-w-64 pl-4">
                      <PersonCell person={{ ...p, company: null }} />
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden md:table-cell">{p.company}</TableCell>
                    <TableCell>
                      <DegreeBadge degree={p.degree} />
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden tabular-nums sm:table-cell">{p.degree && p.degree > 1 ? p.mutuals : "—"}</TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {p.degree === 1 ? (
                        <StrengthSelect
                          size="sm"
                          value={p.closeness ?? 2}
                          onChange={async (s) => {
                            await api.setCloseness(p.id, s)
                            toast.success(`Updated how well you know ${p.name.split(" ")[0]}`)
                            res.reload()
                          }}
                          className="w-28"
                        />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button asChild variant="ghost" size="sm" className="opacity-60 group-hover:opacity-100">
                        <Link to={`/app/path/${p.id}`}>
                          <Route /> Path
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
        {!res.loading && rows.length === 0 && (
          <EmptyState className="m-4" icon={<NetworkIcon />} title={query ? "No matches" : "Your network is empty"} description={query ? "Try a different name or company." : "Import your LinkedIn connections to see your network here."} />
        )}
      </div>

      {total > PAGE && (
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <span>
            {page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} of {total.toLocaleString()}
          </span>
          <div className="flex gap-1">
            <Button variant="outline" size="icon-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)} aria-label="Previous page">
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="icon-sm" disabled={(page + 1) * PAGE >= total} onClick={() => setPage((p) => p + 1)} aria-label="Next page">
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function GraphView() {
  const { api } = useApp()
  const g = useAsync(() => api.egoGraph(), [api])
  if (g.loading && !g.data) return <Skeleton className="mx-auto aspect-square w-full max-w-[640px] rounded-full" />
  if (!g.data || g.data.nodes.length <= 1) return <EmptyState icon={<Waypoints />} title="Nothing to draw yet" description="Import your connections to see your network graph." />
  return (
    <div className="bg-card rounded-xl border p-4">
      <NetworkGraph graph={g.data} />
    </div>
  )
}

export function NetworkPage() {
  return (
    <Tabs defaultValue="table" className="gap-6">
      <PageHeader
        title="Network"
        description="Everyone within three hops of you. Set how well you know your 1st-degree connections so warm routes rank first."
        actions={
          <TabsList>
            <TabsTrigger value="table">
              <Table2 /> Table
            </TabsTrigger>
            <TabsTrigger value="graph">
              <Waypoints /> Graph
            </TabsTrigger>
          </TabsList>
        }
      />
      <TabsContent value="table">
        <NetworkTable />
      </TabsContent>
      <TabsContent value="graph">
        <GraphView />
      </TabsContent>
    </Tabs>
  )
}
