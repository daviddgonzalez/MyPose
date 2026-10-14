import { useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { Logo } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { isLinkedInProfileUrl } from "@/lib/csv"

export function OnboardingPage() {
  const { api, canUseApp, authReady } = useApp()
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [busy, setBusy] = useState(false)

  if (!authReady) return null
  if (!canUseApp) return <Navigate to="/login" replace />

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.setProfile(name, url)
      navigate("/app/import")
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-sidebar flex min-h-svh flex-col items-center justify-center gap-8 p-4">
      <Logo />
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="text-muted-foreground mb-1 text-xs font-medium">Step 1 of 2</div>
          <CardTitle>Put yourself on the map</CardTitle>
          <CardDescription>
            Your LinkedIn URL is how we match you with people who already have you in their connections. It's what links your network to theirs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Full name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Jordan Avery" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="url">LinkedIn profile URL</Label>
              <Input id="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.linkedin.com/in/your-handle" aria-invalid={!!url && !isLinkedInProfileUrl(url)} />
              <p className="text-muted-foreground text-xs">On LinkedIn, open your profile and copy the address from the browser bar.</p>
            </div>
            <Button type="submit" disabled={busy || !isLinkedInProfileUrl(url)}>
              {busy ? "Saving…" : "Continue"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
