import { createClient, type SupabaseClient } from "@supabase/supabase-js"

import type { Api } from "./api"
import type { EgoGraph, ImportRecord, NetworkPerson, PathEdge, Person, Profile, Stats, Target } from "./types"

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const key = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? import.meta.env.VITE_SUPABASE_ANON_KEY) as string | undefined

/** Null when the app is deployed without Supabase credentials (demo-only mode). */
export const supabase: SupabaseClient | null = url && key ? createClient(url, key) : null

const CHUNK = 500
const PERSON_COLS = "id, name, company, title, linkedin_url"

function check<T>({ data, error }: { data: T; error: { message: string } | null }): T {
  if (error) throw new Error(error.message)
  return data
}

export function createSupabaseApi(sb: SupabaseClient): Api {
  const uid = async () => {
    const { data } = await sb.auth.getUser()
    if (!data.user) throw new Error("Not signed in")
    return data.user.id
  }

  return {
    mode: "live",

    async getProfile() {
      const id = await uid()
      return check(await sb.from("profiles").select("id, person_id, full_name, linkedin_url").eq("id", id).maybeSingle()) as Profile | null
    },

    async setProfile(name, linkedinUrl) {
      return check(await sb.rpc("set_my_profile", { p_name: name, p_linkedin_url: linkedinUrl })) as Profile
    },

    async importConnections(rows, filename, onProgress) {
      let total = 0
      for (let i = 0; i < rows.length; i += CHUNK) {
        total += check(await sb.rpc("import_connections", { p_rows: rows.slice(i, i + CHUNK) })) as number
        onProgress?.(Math.min(i + CHUNK, rows.length))
      }
      check(await sb.from("imports").insert({ filename, row_count: rows.length }))
      return total
    },

    async listImports() {
      return (check(await sb.from("imports").select("id, filename, row_count, created_at").order("created_at", { ascending: false })) ?? []) as ImportRecord[]
    },

    async searchNetwork({ query, degree, limit = 50, offset = 0 }) {
      const data = check(
        await sb.rpc("search_network", { p_query: query || null, p_degree: degree ?? null, p_limit: limit, p_offset: offset })
      ) as (NetworkPerson & { total: number })[]
      return { rows: data, total: data[0]?.total ?? 0 }
    },

    async getPeople(ids) {
      if (!ids.length) return []
      return check(await sb.from("people").select(PERSON_COLS).in("id", ids)) as Person[]
    },

    async pathGraph(targetId) {
      return check(await sb.rpc("path_graph", { p_target: targetId })) as PathEdge[]
    },

    async egoGraph() {
      return check(await sb.rpc("ego_graph", { p_limit: 150 })) as EgoGraph
    },

    async stats() {
      return check(await sb.rpc("network_stats")) as Stats
    },

    async listTargets() {
      const data = check(
        await sb.from("targets").select(`note, created_at, person:people(${PERSON_COLS})`).order("created_at", { ascending: false })
      ) as unknown as Target[]
      return data.filter((t) => t.person)
    },

    async addTarget(personId, note) {
      check(await sb.from("targets").upsert({ person_id: personId, note: note || null }))
    },

    async removeTarget(personId) {
      check(await sb.from("targets").delete().eq("person_id", personId))
    },

    async ensurePerson({ name, linkedinUrl, company, title }) {
      return check(
        await sb.rpc("ensure_person", { p_name: name, p_linkedin_url: linkedinUrl || null, p_company: company || null, p_title: title || null })
      ) as string
    },

    async addLink(a, b, strength) {
      check(await sb.rpc("add_link", { p_a: a, p_b: b, p_strength: strength }))
    },

    async setCloseness(personId, strength) {
      check(await sb.rpc("set_closeness", { p_person: personId, p_strength: strength }))
    },

    async resetData() {
      check(await sb.rpc("reset_my_data"))
    },
  }
}
