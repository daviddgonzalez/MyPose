import { useEffect, useRef, useState } from "react"
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from "react-router-dom"
import { LogOut, Menu, Moon, Search, Sparkles, Sun } from "lucide-react"

import { useApp } from "@/app-context"
import { CommandMenu } from "@/components/command-menu"
import { Logo } from "@/components/logo"
import { Kbd } from "@/components/page"
import { PersonAvatar } from "@/components/person"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useAsync } from "@/hooks/use-async"
import { useTheme } from "@/hooks/use-theme"
import { NAV } from "@/lib/nav"
import type { Profile } from "@/lib/types"
import { cn } from "@/lib/utils"

interface LayoutCtx {
  profile: Profile
  reloadProfile(): void
  openSearch(): void
}

// eslint-disable-next-line react-refresh/only-export-components
export const useLayout = () => useOutletContext<LayoutCtx>()

function SidebarNav({ onNavigate, openSearch }: { onNavigate?: () => void; openSearch: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5">
      <button
        onClick={openSearch}
        className="text-muted-foreground hover:bg-accent hover:text-foreground mb-3 flex h-8 items-center gap-2 rounded-md border px-2.5 text-sm transition-colors"
      >
        <Search className="size-4" />
        <span className="flex-1 text-left">Find someone…</span>
        <Kbd>⌘K</Kbd>
      </button>
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/app"}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
              isActive ? "bg-accent text-foreground font-medium" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            )
          }
        >
          <n.icon className="size-4" />
          <span className="flex-1">{n.label}</span>
          <span className="text-muted-foreground/70 hidden text-[10px] tracking-widest group-hover:inline">G {n.key.toUpperCase()}</span>
        </NavLink>
      ))}
    </nav>
  )
}

function UserMenu({ profile }: { profile: Profile }) {
  const { api, session, signOut } = useApp()
  const { resolved, setTheme } = useTheme()
  const navigate = useNavigate()
  const name = profile.full_name ?? session?.user.email ?? "You"
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="hover:bg-accent flex w-full items-center gap-2.5 rounded-md p-1.5 text-left transition-colors">
          <PersonAvatar name={name} className="size-7" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{name}</div>
            <div className="text-muted-foreground truncate text-xs">{api.mode === "demo" ? "Demo network" : session?.user.email}</div>
          </div>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">Signed in as {name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setTheme(resolved === "dark" ? "light" : "dark")}>
          {resolved === "dark" ? <Sun /> : <Moon />} {resolved === "dark" ? "Light" : "Dark"} theme
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={async () => {
            await signOut()
            navigate("/")
          }}
        >
          <LogOut /> {api.mode === "demo" ? "Leave demo" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppLayout() {
  const { api, authReady, canUseApp, demoOnly } = useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchOpen, setSearchOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const profile = useAsync(() => (canUseApp ? api.getProfile() : Promise.resolve(null)), [api, canUseApp])
  const pendingG = useRef(0)

  // ⌘K opens search; Linear-style "G then letter" jumps between pages.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setSearchOpen((o) => !o)
        return
      }
      const el = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || el.closest("input, textarea, select, [contenteditable], [role=dialog]")) return
      if (e.key === "/") {
        e.preventDefault()
        setSearchOpen(true)
      } else if (e.key.toLowerCase() === "g") {
        pendingG.current = Date.now()
      } else if (Date.now() - pendingG.current < 1000) {
        const hit = NAV.find((n) => n.key === e.key.toLowerCase())
        if (hit) navigate(hit.to)
        pendingG.current = 0
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [navigate])

  if (!authReady) return null
  if (!canUseApp) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (profile.loading && !profile.data) {
    return (
      <div className="p-8">
        <Skeleton className="h-8 w-48" />
      </div>
    )
  }
  if (!profile.data?.person_id) return <Navigate to="/onboarding" replace />

  const ctx: LayoutCtx = { profile: profile.data, reloadProfile: profile.reload, openSearch: () => setSearchOpen(true) }

  const sidebar = (onNavigate?: () => void) => (
    <div className="flex h-full flex-col gap-6 p-3">
      <Link to="/" className="px-1.5 pt-1" onClick={onNavigate}>
        <Logo />
      </Link>
      <SidebarNav onNavigate={onNavigate} openSearch={() => setSearchOpen(true)} />
      <div className="mt-auto">
        <UserMenu profile={profile.data!} />
      </div>
    </div>
  )

  return (
    <div className="bg-sidebar min-h-svh md:flex">
      <aside className="sticky top-0 hidden h-svh w-60 shrink-0 md:block">{sidebar()}</aside>
      <header className="bg-background/80 sticky top-0 z-30 flex h-12 items-center gap-2 border-b px-3 backdrop-blur md:hidden">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Open menu">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="bg-sidebar w-64 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            {sidebar(() => setMobileOpen(false))}
          </SheetContent>
        </Sheet>
        <Logo />
        <Button variant="ghost" size="icon-sm" className="ml-auto" aria-label="Search" onClick={() => setSearchOpen(true)}>
          <Search />
        </Button>
      </header>
      <main className="bg-background min-w-0 flex-1 md:my-2 md:mr-2 md:rounded-xl md:border md:shadow-xs">
        {api.mode === "demo" && (
          <div className="bg-brand-soft text-foreground flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2 text-sm md:rounded-t-xl md:px-8">
            <Sparkles className="text-primary size-4" />
            <span>You're exploring a sample network with fictional people.</span>
            {!demoOnly && (
              <Link to="/login" className="text-primary font-medium hover:underline">
                Sign in to build yours →
              </Link>
            )}
          </div>
        )}
        <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">
          <Outlet context={ctx} />
        </div>
      </main>
      <CommandMenu open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  )
}
