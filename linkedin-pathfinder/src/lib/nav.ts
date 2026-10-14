import { Home, Network, Settings, Target, Upload } from "lucide-react"

export const NAV = [
  { to: "/app", label: "Overview", icon: Home, key: "o" },
  { to: "/app/targets", label: "Targets", icon: Target, key: "t" },
  { to: "/app/network", label: "Network", icon: Network, key: "n" },
  { to: "/app/import", label: "Import", icon: Upload, key: "i" },
  { to: "/app/settings", label: "Settings", icon: Settings, key: "s" },
] as const
