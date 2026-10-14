import Papa from "papaparse"

import type { ConnectionRow } from "./types"

/**
 * Parse LinkedIn's Connections.csv export. The file starts with a few "Notes:" lines
 * before the real header row, so we locate the header first.
 */
export function parseConnectionsCsv(text: string): ConnectionRow[] {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/)
  const headerAt = lines.findIndex((l) => /first name/i.test(l) && /last name/i.test(l))
  if (headerAt < 0) {
    throw new Error("Couldn't find the “First Name, Last Name” header. Is this LinkedIn's Connections.csv?")
  }
  const { data } = Papa.parse<Record<string, string>>(lines.slice(headerAt).join("\n"), {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.trim().toLowerCase(),
  })
  const rows: ConnectionRow[] = []
  for (const r of data) {
    const name = `${r["first name"] ?? ""} ${r["last name"] ?? ""}`.trim().replace(/\s+/g, " ")
    if (!name) continue
    rows.push({ name, url: (r["url"] ?? "").trim(), company: (r["company"] ?? "").trim(), title: (r["position"] ?? "").trim() })
  }
  return rows
}

export function isLinkedInProfileUrl(url: string) {
  return /linkedin\.com\/in\/[^/?#]+/i.test(url)
}
