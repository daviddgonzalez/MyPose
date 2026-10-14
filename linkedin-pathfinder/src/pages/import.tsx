import { useRef, useState } from "react"
import { CheckCircle2, FileSpreadsheet, Link2, Upload } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { PageHeader } from "@/components/page"
import { PersonPicker, type PickedPerson } from "@/components/person-picker"
import { StrengthSelect } from "@/components/strength-select"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAsync } from "@/hooks/use-async"
import { parseConnectionsCsv } from "@/lib/csv"
import type { ConnectionRow, Strength } from "@/lib/types"
import { cn } from "@/lib/utils"

function Dropzone() {
  const { api } = useApp()
  const input = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [file, setFile] = useState<{ name: string; rows: ConnectionRow[] } | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const history = useAsync(() => api.listImports(), [api])

  const read = async (f: File | undefined) => {
    if (!f) return
    try {
      const rows = parseConnectionsCsv(await f.text())
      if (!rows.length) throw new Error("That file has no connections in it.")
      setFile({ name: f.name, rows })
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  const upload = async () => {
    if (!file) return
    setProgress(0)
    try {
      const n = await api.importConnections(file.rows, file.name, setProgress)
      toast.success(`Imported ${n.toLocaleString()} connections`)
      setFile(null)
      history.reload()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setProgress(null)
    }
  }

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Upload Connections.csv</CardTitle>
          <CardDescription>Re-upload any time. Duplicates are merged, so it's safe to import again after you make new connections.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {!file ? (
            <button
              onClick={() => input.current?.click()}
              onDragOver={(e) => (e.preventDefault(), setDrag(true))}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDrag(false)
                read(e.dataTransfer.files[0])
              }}
              className={cn(
                "hover:bg-muted/40 flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center transition-colors",
                drag && "border-primary bg-brand-soft/50"
              )}
            >
              <div className="bg-muted text-muted-foreground mb-3 flex size-10 items-center justify-center rounded-lg">
                <Upload className="size-5" />
              </div>
              <span className="text-sm font-medium">Drop your Connections.csv here</span>
              <span className="text-muted-foreground mt-1 text-xs">or click to browse</span>
            </button>
          ) : (
            <div className="grid gap-4">
              <div className="flex items-center gap-3 rounded-lg border p-3">
                <FileSpreadsheet className="text-primary size-5" />
                <div className="flex-1">
                  <div className="text-sm font-medium">{file.name}</div>
                  <div className="text-muted-foreground text-xs">{file.rows.length.toLocaleString()} connections found</div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setFile(null)} disabled={progress !== null}>
                  Change
                </Button>
              </div>
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-3">Name</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead className="hidden sm:table-cell">Company</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {file.rows.slice(0, 5).map((r, i) => (
                      <TableRow key={i}>
                        <TableCell className="pl-3 font-medium">{r.name}</TableCell>
                        <TableCell className="text-muted-foreground max-w-48 truncate">{r.title}</TableCell>
                        <TableCell className="text-muted-foreground hidden sm:table-cell">{r.company}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {file.rows.length > 5 && <div className="text-muted-foreground border-t px-3 py-2 text-xs">…and {(file.rows.length - 5).toLocaleString()} more</div>}
              </div>
              <Button onClick={upload} disabled={progress !== null} className="w-fit">
                {progress !== null ? `Importing… ${Math.round((progress / file.rows.length) * 100)}%` : `Import ${file.rows.length.toLocaleString()} connections`}
              </Button>
            </div>
          )}
          <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={(e) => (read(e.target.files?.[0]), (e.target.value = ""))} />
        </CardContent>
      </Card>

      {!!history.data?.length && (
        <Card className="gap-0 pb-0">
          <CardHeader className="pb-4">
            <CardTitle className="text-sm">Import history</CardTitle>
          </CardHeader>
          <ul className="divide-y border-t">
            {history.data.map((h) => (
              <li key={h.id} className="flex items-center gap-3 px-6 py-3 text-sm">
                <CheckCircle2 className="text-success size-4" />
                <span className="flex-1 font-medium">{h.filename ?? "Upload"}</span>
                <span className="text-muted-foreground tabular-nums">{h.row_count.toLocaleString()} rows</span>
                <span className="text-muted-foreground hidden sm:inline">{new Date(h.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function ManualLink() {
  const { api } = useApp()
  const [a, setA] = useState<PickedPerson | null>(null)
  const [b, setB] = useState<PickedPerson | null>(null)
  const [strength, setStrength] = useState<Strength>(2)
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!a || !b) return
    setBusy(true)
    try {
      const ida = a.id ?? (await api.ensurePerson({ name: a.name }))
      const idb = b.id ?? (await api.ensurePerson({ name: b.name }))
      await api.addLink(ida, idb, strength)
      toast.success(`Noted: ${a.name} knows ${b.name}`)
      setA(null)
      setB(null)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Link2 className="size-4" /> Add a link by hand
        </CardTitle>
        <CardDescription>Know two people are connected? Record it. Private to you, and used in your routes.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <PersonPicker value={a} onChange={setA} placeholder="Person" />
        <div className="text-muted-foreground text-center text-xs">knows</div>
        <PersonPicker value={b} onChange={setB} placeholder="Person" />
        <StrengthSelect value={strength} onChange={setStrength} className="w-full" />
        <Button variant="outline" onClick={save} disabled={!a || !b || busy}>
          Add link
        </Button>
      </CardContent>
    </Card>
  )
}

const STEPS = [
  "On LinkedIn, open Settings & Privacy → Data privacy.",
  "Choose “Get a copy of your data”, pick “Connections”, and request the archive.",
  "LinkedIn emails you a download link, usually within 10 minutes.",
  "Unzip it and upload Connections.csv here.",
]

export function ImportPage() {
  return (
    <div className="grid gap-6">
      <PageHeader title="Import" description="Your connections become part of the shared network, so you and every other member can find more paths." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Dropzone />
        <div className="grid h-fit gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Getting your export</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="grid gap-3 text-sm">
                {STEPS.map((s, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium">{i + 1}</span>
                    <span className="text-muted-foreground">{s}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <ManualLink />
        </div>
      </div>
    </div>
  )
}
