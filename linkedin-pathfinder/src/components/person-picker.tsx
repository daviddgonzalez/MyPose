import { useEffect, useState } from "react"
import { Check, ChevronsUpDown, Plus } from "lucide-react"

import { useApp } from "@/app-context"
import { DegreeBadge, PersonCell } from "@/components/person"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import type { NetworkPerson } from "@/lib/types"
import { cn } from "@/lib/utils"

export type PickedPerson = { id: string; name: string } | { id: null; name: string }

/** Search the directory; if nobody matches, offer to use the typed name as a new person. */
export function PersonPicker({
  value,
  onChange,
  placeholder = "Search people…",
  degree,
  allowCreate = true,
  className,
}: {
  value: PickedPerson | null
  onChange: (p: PickedPerson | null) => void
  placeholder?: string
  degree?: 1 | 2 | 3
  allowCreate?: boolean
  className?: string
}) {
  const { api } = useApp()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [rows, setRows] = useState<NetworkPerson[]>([])

  useEffect(() => {
    if (!open) return
    let live = true
    const t = setTimeout(() => api.searchNetwork({ query: q, degree, limit: 20 }).then((r) => live && setRows(r.rows)), 150)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [api, q, open, degree])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className={cn("w-full justify-between font-normal", className)}>
          <span className={cn("truncate", !value && "text-muted-foreground")}>{value?.name ?? placeholder}</span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Type a name or company…" value={q} onValueChange={setQ} />
          <CommandList>
            <CommandEmpty>{q ? "No one found." : "Start typing to search."}</CommandEmpty>
            {rows.length > 0 && (
              <CommandGroup heading="People">
                {rows.map((p) => (
                  <CommandItem
                    key={p.id}
                    value={p.id}
                    onSelect={() => {
                      onChange({ id: p.id, name: p.name })
                      setOpen(false)
                    }}
                  >
                    <PersonCell person={p} size="sm" className="flex-1" />
                    <DegreeBadge degree={p.degree} />
                    <Check className={cn("ml-1", value?.id === p.id ? "opacity-100" : "opacity-0")} />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {allowCreate && q.trim() && (
              <CommandGroup heading="Not on the list?">
                <CommandItem
                  value={`new:${q}`}
                  onSelect={() => {
                    onChange({ id: null, name: q.trim() })
                    setOpen(false)
                  }}
                >
                  <Plus />
                  Add “{q.trim()}” as a new person
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
