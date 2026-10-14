import { useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { PersonPicker, type PickedPerson } from "@/components/person-picker"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function AddTargetDialog({ children, onAdded }: { children: ReactNode; onAdded?: () => void }) {
  const { api } = useApp()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<PickedPerson | null>(null)
  const [url, setUrl] = useState("")
  const [company, setCompany] = useState("")
  const [title, setTitle] = useState("")
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setPicked(null)
    setUrl("")
    setCompany("")
    setTitle("")
    setNote("")
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!picked) return
    setBusy(true)
    try {
      const id = picked.id ?? (await api.ensurePerson({ name: picked.name, linkedinUrl: url, company, title }))
      await api.addTarget(id, note)
      toast.success(`Added ${picked.name} to your targets`)
      setOpen(false)
      reset()
      onAdded?.()
      navigate(`/app/path/${id}`)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (setOpen(o), o || reset())}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a target</DialogTitle>
          <DialogDescription>Who do you want to reach? Search the network, or add someone new.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-2">
            <Label>Person</Label>
            <PersonPicker value={picked} onChange={setPicked} placeholder="Search by name or company…" />
          </div>
          {picked && picked.id === null && (
            <div className="bg-muted/40 grid gap-3 rounded-lg border p-3">
              <p className="text-muted-foreground text-xs">
                Paste their LinkedIn URL so they match up when someone uploads a connection list that includes them.
              </p>
              <div className="grid gap-2">
                <Label htmlFor="t-url">LinkedIn URL</Label>
                <Input id="t-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.linkedin.com/in/…" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-2">
                  <Label htmlFor="t-title">Title</Label>
                  <Input id="t-title" value={title} onChange={(e) => setTitle(e.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="t-company">Company</Label>
                  <Input id="t-company" value={company} onChange={(e) => setCompany(e.target.value)} />
                </div>
              </div>
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="t-note">Note (optional)</Label>
            <Input id="t-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you want to reach them" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!picked || busy}>
              {busy ? "Adding…" : "Add target"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
