import { useEffect, useState } from "react"

export type Theme = "light" | "dark" | "system"
const KEY = "pf-theme"

function read(): Theme {
  try {
    return (localStorage.getItem(KEY) as Theme) || "system"
  } catch {
    return "system"
  }
}

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  document.documentElement.classList.toggle("dark", dark)
  return dark ? "dark" : "light"
}

const listeners = new Set<(t: Theme) => void>()

export function initTheme() {
  apply(read())
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => apply(read()))
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read)
  useEffect(() => {
    listeners.add(setThemeState)
    return () => void listeners.delete(setThemeState)
  }, [])
  const setTheme = (t: Theme) => {
    try {
      localStorage.setItem(KEY, t)
    } catch {
      /* storage unavailable */
    }
    apply(t)
    listeners.forEach((l) => l(t))
  }
  const resolved = typeof document !== "undefined" && document.documentElement.classList.contains("dark") ? "dark" : "light"
  return { theme, resolved, setTheme }
}
