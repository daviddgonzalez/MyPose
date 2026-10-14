import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppProvider } from "@/app-context"
import { AppLayout } from "@/components/app-layout"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { LandingPage } from "@/pages/landing"
import { LoginPage } from "@/pages/login"
import { OnboardingPage } from "@/pages/onboarding"

const page = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] })))
const OverviewPage = page(() => import("@/pages/overview"), "OverviewPage")
const TargetsPage = page(() => import("@/pages/targets"), "TargetsPage")
const PathPage = page(() => import("@/pages/path"), "PathPage")
const NetworkPage = page(() => import("@/pages/network"), "NetworkPage")
const ImportPage = page(() => import("@/pages/import"), "ImportPage")
const SettingsPage = page(() => import("@/pages/settings"), "SettingsPage")

export default function App() {
  return (
    <AppProvider>
      <TooltipProvider>
        <BrowserRouter>
          <Suspense fallback={null}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<OverviewPage />} />
              <Route path="targets" element={<TargetsPage />} />
              <Route path="path/:id" element={<PathPage />} />
              <Route path="network" element={<NetworkPage />} />
              <Route path="import" element={<ImportPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </AppProvider>
  )
}
