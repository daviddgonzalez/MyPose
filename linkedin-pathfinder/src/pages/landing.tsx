import { Link, useNavigate } from "react-router-dom"
import { ArrowRight, GitBranch, Lock, MessageSquareText, Network, Upload, UsersRound } from "lucide-react"

import { useApp } from "@/app-context"
import { Logo } from "@/components/logo"
import { DegreeBadge, PersonAvatar } from "@/components/person"
import { RouteChain } from "@/components/route-chain"
import { Button } from "@/components/ui/button"
import type { Person } from "@/lib/types"

const SAMPLE: Person[] = [
  { id: "me", name: "You", company: null, title: null, linkedin_url: null },
  { id: "a", name: "Maya Chen", company: "Lumen Labs", title: "Design Lead", linkedin_url: null },
  { id: "b", name: "Alex Kim", company: "Halcyon AI", title: "Engineer", linkedin_url: null },
  { id: "c", name: "Priya Raman", company: "Halcyon AI", title: "Head of Talent", linkedin_url: null },
]
const SAMPLE_PEOPLE = new Map(SAMPLE.map((p) => [p.id, p]))

function HeroCard() {
  return (
    <div className="bg-card relative rounded-2xl border p-5 shadow-[0_1px_0_0_var(--border),0_24px_48px_-24px_rgb(0_0_0/0.18)] sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <PersonAvatar name="Priya Raman" className="size-10" />
          <div>
            <div className="font-semibold">Priya Raman</div>
            <div className="text-muted-foreground text-sm">Head of Talent · Halcyon AI</div>
          </div>
        </div>
        <DegreeBadge degree={3} />
      </div>
      <div className="mt-6 overflow-x-auto">
        <RouteChain route={{ path: ["me", "a", "b", "c"], strengths: [3, 3, 2], cost: 4, hops: 3 }} people={SAMPLE_PEOPLE} />
      </div>
      <div className="bg-muted/60 mt-5 rounded-lg border p-3.5 text-sm">
        <span className="font-medium">Next step:</span> message <span className="font-medium">Maya Chen</span> and ask for an intro to{" "}
        <span className="font-medium">Alex Kim</span>.
      </div>
      <div className="text-muted-foreground mt-4 flex items-center gap-4 text-xs">
        <span>3 hops</span>
        <span>2 other routes</span>
        <span className="ml-auto">Warmest route first</span>
      </div>
    </div>
  )
}

const FEATURES = [
  { icon: Network, title: "A network that grows with every upload", body: "Each member's connections join one shared graph, so your paths reach further than LinkedIn shows you." },
  { icon: GitBranch, title: "Warmest route first", body: "Fewest hops wins. Among equally short routes, the one through people you know best ranks first." },
  { icon: MessageSquareText, title: "Know exactly who to ask", body: "Every target gets a clear next step and a ready-to-send intro request you can edit and copy." },
  { icon: Lock, title: "Private by design", body: "No one can browse your connection list. People see only the hops on their own route." },
]

const STEPS = [
  { icon: Upload, title: "Upload Connections.csv", body: "Export your connections from LinkedIn's data download. It takes a couple of minutes." },
  { icon: UsersRound, title: "Pick who you want to reach", body: "Search everyone in the shared network, or add someone by name and LinkedIn URL." },
  { icon: ArrowRight, title: "Follow the path", body: "See who to message first, who they'll introduce you to, and every alternative route." },
]

export function LandingPage() {
  const { canUseApp, demoOnly, enterDemo } = useApp()
  const navigate = useNavigate()
  const tryDemo = () => {
    enterDemo()
    navigate("/app")
  }

  return (
    <div className="min-h-svh">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-8">
        <Logo />
        <div className="flex items-center gap-2">
          {canUseApp ? (
            <Button asChild size="sm">
              <Link to="/app">Open app</Link>
            </Button>
          ) : (
            <>
              {!demoOnly && (
                <Button asChild variant="ghost" size="sm">
                  <Link to="/login">Sign in</Link>
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={tryDemo}>
                Try the demo
              </Button>
            </>
          )}
        </div>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-12 pb-20 md:grid-cols-[1.05fr_1fr] md:px-8 md:pt-20">
        <div>
          <div className="text-muted-foreground mb-5 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs">
            <span className="bg-primary size-1.5 rounded-full" /> Warm intros, mapped
          </div>
          <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight text-balance sm:text-5xl">Find the warmest path to anyone on LinkedIn.</h1>
          <p className="text-muted-foreground mt-5 max-w-lg text-lg text-pretty">
            Upload your connections and Pathfinder maps them against everyone else's. Then it tells you who to message first to get introduced.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" asChild={!demoOnly} onClick={demoOnly ? tryDemo : undefined}>
              {demoOnly ? <span>Explore the demo</span> : <Link to={canUseApp ? "/app" : "/login"}>Get started — it's free</Link>}
            </Button>
            {!demoOnly && !canUseApp && (
              <Button size="lg" variant="outline" onClick={tryDemo}>
                See a sample network
              </Button>
            )}
          </div>
        </div>
        <HeroCard />
      </section>

      <section className="border-y bg-sidebar">
        <div className="mx-auto grid max-w-6xl gap-px px-4 py-16 sm:grid-cols-2 md:px-8 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.title} className="p-4">
              <f.icon className="text-primary size-5" />
              <h3 className="mt-4 text-sm font-semibold">{f.title}</h3>
              <p className="text-muted-foreground mt-1.5 text-sm">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 md:px-8">
        <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
        <ol className="mt-8 grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="bg-card rounded-xl border p-5">
              <div className="text-muted-foreground flex items-center justify-between text-xs font-medium">
                <span>Step {i + 1}</span>
                <s.icon className="size-4" />
              </div>
              <h3 className="mt-6 font-semibold">{s.title}</h3>
              <p className="text-muted-foreground mt-1.5 text-sm">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <footer className="text-muted-foreground mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 border-t px-4 py-8 text-xs md:px-8">
        <Logo className="text-foreground text-sm" />
        <span>Not affiliated with LinkedIn. Uses only the data export LinkedIn gives you.</span>
      </footer>
    </div>
  )
}
