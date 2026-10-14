import { useState } from "react"
import { Link, Navigate, useNavigate } from "react-router-dom"
import { MailCheck } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { Logo } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { supabase } from "@/lib/supabase"

export function LoginPage() {
  const { session, demoOnly, enterDemo } = useApp()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  if (demoOnly) return <Navigate to="/" replace />
  if (session) return <Navigate to="/app" replace />

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const { error } = await supabase!.auth.signInWithOtp({ email, options: { emailRedirectTo: `${window.location.origin}/app` } })
    setBusy(false)
    if (error) toast.error(error.message)
    else setSent(true)
  }

  return (
    <div className="bg-sidebar flex min-h-svh flex-col items-center justify-center gap-8 p-4">
      <Link to="/">
        <Logo />
      </Link>
      <Card className="w-full max-w-sm">
        {sent ? (
          <CardContent className="flex flex-col items-center py-4 text-center">
            <div className="bg-brand-soft text-primary mb-4 flex size-10 items-center justify-center rounded-lg">
              <MailCheck className="size-5" />
            </div>
            <h1 className="font-semibold">Check your email</h1>
            <p className="text-muted-foreground mt-1 text-sm">
              We sent a sign-in link to <span className="text-foreground font-medium">{email}</span>.
            </p>
            <Button variant="link" className="mt-2" onClick={() => setSent(false)}>
              Use a different email
            </Button>
          </CardContent>
        ) : (
          <>
            <CardHeader>
              <CardTitle>Sign in to Pathfinder</CardTitle>
              <CardDescription>We'll email you a magic link. No password needed.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={send} className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" required autoFocus placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <Button type="submit" disabled={busy}>
                  {busy ? "Sending…" : "Send magic link"}
                </Button>
              </form>
            </CardContent>
          </>
        )}
      </Card>
      <button
        className="text-muted-foreground hover:text-foreground text-sm"
        onClick={() => {
          enterDemo()
          navigate("/app")
        }}
      >
        Just looking? Explore the demo network →
      </button>
    </div>
  )
}
