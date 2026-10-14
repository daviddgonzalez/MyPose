import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Monitor, Moon, Sun } from "lucide-react"
import { toast } from "sonner"

import { useApp } from "@/app-context"
import { useLayout } from "@/components/app-layout"
import { PageHeader } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useTheme, type Theme } from "@/hooks/use-theme"
import { isLinkedInProfileUrl } from "@/lib/csv"
import { cn } from "@/lib/utils"

export function SettingsPage() {
  const { api, signOut } = useApp()
  const { profile, reloadProfile } = useLayout()
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const [name, setName] = useState(profile.full_name ?? "")
  const [url, setUrl] = useState(profile.linkedin_url ?? "")

  const save = async () => {
    try {
      await api.setProfile(name, url)
      toast.success("Profile saved")
      reloadProfile()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title="Settings" />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Profile</CardTitle>
          <CardDescription>Your LinkedIn URL connects you to everyone who has you in their connections.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="s-name">Full name</Label>
            <Input id="s-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="s-url">LinkedIn profile URL</Label>
            <Input id="s-url" value={url} onChange={(e) => setUrl(e.target.value)} aria-invalid={!!url && !isLinkedInProfileUrl(url)} />
          </div>
        </CardContent>
        <CardFooter className="border-t">
          <Button onClick={save} disabled={!name || !isLinkedInProfileUrl(url)}>
            Save
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Appearance</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-3 gap-2">
          {([
            ["light", Sun, "Light"],
            ["dark", Moon, "Dark"],
            ["system", Monitor, "System"],
          ] as [Theme, typeof Sun, string][]).map(([t, Icon, label]) => (
            <button
              key={t}
              onClick={() => setTheme(t)}
              className={cn("hover:bg-muted/50 flex flex-col items-center gap-2 rounded-lg border p-3 text-sm transition-colors", theme === t && "border-primary ring-primary/15 ring-4")}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Privacy</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground grid gap-2 text-sm">
          <p>Members can never browse your connection list. When someone's shortest route to a target passes through you, they see only the people on that route, just as LinkedIn shows mutual connections.</p>
          <p>Links you add by hand and how well you know people stay private and only affect your own routes.</p>
        </CardContent>
      </Card>

      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="text-sm">Danger zone</CardTitle>
          <CardDescription>Remove your uploads, links, targets and profile link from the network.</CardDescription>
        </CardHeader>
        <CardFooter className="gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="destructive">Delete my data</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete your data?</DialogTitle>
                <DialogDescription>Your imported connections, manual links, targets and profile link will be removed. This can't be undone.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button
                  variant="destructive"
                  onClick={async () => {
                    await api.resetData()
                    toast.success("Your data was deleted")
                    if (api.mode === "live") navigate("/onboarding")
                    else reloadProfile()
                  }}
                >
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Button
            variant="ghost"
            onClick={async () => {
              await signOut()
              navigate("/")
            }}
          >
            {api.mode === "demo" ? "Leave demo" : "Sign out"}
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}
