import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Moon, Sun } from "lucide-react"

import { useApp } from "@/app-context"
import { DegreeBadge, PersonCell } from "@/components/person"
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from "@/components/ui/command"
import { useTheme } from "@/hooks/use-theme"
import { NAV } from "@/lib/nav"
import type { NetworkPerson } from "@/lib/types"

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { api } = useApp()
  const navigate = useNavigate()
  const { resolved, setTheme } = useTheme()
  const [q, setQ] = useState("")
  const [people, setPeople] = useState<NetworkPerson[]>([])

  useEffect(() => {
    if (!open) return
    let live = true
    const t = setTimeout(() => api.searchNetwork({ query: q, limit: 8 }).then((r) => live && setPeople(r.rows)), 120)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [api, q, open])

  const go = (to: string) => {
    onOpenChange(false)
    setQ("")
    navigate(to)
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Search" description="Find a person or jump to a page">
      <CommandInput placeholder="Find someone to reach, or jump to…" value={q} onValueChange={setQ} />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {people.length > 0 && (
          <CommandGroup heading={q ? "People" : "Closest in your network"}>
            {people.map((p) => (
              <CommandItem key={p.id} value={`person-${p.id}`} onSelect={() => go(`/app/path/${p.id}`)}>
                <PersonCell person={p} size="sm" className="flex-1" />
                <DegreeBadge degree={p.degree} />
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading="Go to">
          {NAV.filter((n) => !q || n.label.toLowerCase().includes(q.toLowerCase())).map((n) => (
            <CommandItem key={n.to} value={n.to} onSelect={() => go(n.to)}>
              <n.icon />
              {n.label}
              <CommandShortcut>G {n.key.toUpperCase()}</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
        {(!q || "theme".includes(q.toLowerCase())) && (
          <CommandGroup heading="Preferences">
            <CommandItem
              value="theme"
              onSelect={() => {
                setTheme(resolved === "dark" ? "light" : "dark")
                onOpenChange(false)
              }}
            >
              {resolved === "dark" ? <Sun /> : <Moon />}
              Switch to {resolved === "dark" ? "light" : "dark"} theme
            </CommandItem>
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  )
}
