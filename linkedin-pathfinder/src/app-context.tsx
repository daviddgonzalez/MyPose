import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import type { Session } from "@supabase/supabase-js"

import type { Api } from "@/lib/api"
import { createDemoApi } from "@/lib/demo"
import { createSupabaseApi, supabase } from "@/lib/supabase"

const DEMO_KEY = "pf-demo"

interface AppState {
  api: Api
  /** True when the app was deployed without Supabase credentials. */
  demoOnly: boolean
  session: Session | null
  authReady: boolean
  /** Signed in (live) or browsing the demo. */
  canUseApp: boolean
  enterDemo(): void
  exitDemo(): void
  signOut(): Promise<void>
}

const Ctx = createContext<AppState | null>(null)

function readDemoFlag() {
  try {
    return sessionStorage.getItem(DEMO_KEY) === "1"
  } catch {
    return false
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const demoOnly = !supabase
  const [demo, setDemo] = useState(() => demoOnly || readDemoFlag())
  const [session, setSession] = useState<Session | null>(null)
  const [authReady, setAuthReady] = useState(demoOnly)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setAuthReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  const api = useMemo(() => (demo || !supabase ? createDemoApi() : createSupabaseApi(supabase)), [demo])

  const value: AppState = {
    api,
    demoOnly,
    session,
    authReady: demo || authReady,
    canUseApp: demo || !!session,
    enterDemo() {
      try {
        sessionStorage.setItem(DEMO_KEY, "1")
      } catch {
        /* ignore */
      }
      setDemo(true)
    },
    exitDemo() {
      try {
        sessionStorage.removeItem(DEMO_KEY)
        sessionStorage.removeItem("pf-demo-state")
      } catch {
        /* ignore */
      }
      setDemo(demoOnly)
    },
    async signOut() {
      if (demo) value.exitDemo()
      else await supabase?.auth.signOut()
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApp() {
  const v = useContext(Ctx)
  if (!v) throw new Error("useApp outside AppProvider")
  return v
}
