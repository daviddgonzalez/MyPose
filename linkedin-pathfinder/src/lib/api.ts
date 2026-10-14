import type { ConnectionRow, EgoGraph, ImportRecord, NetworkPerson, PathEdge, Person, Profile, Stats, Strength, Target } from "./types"

export interface SearchParams {
  query?: string
  degree?: 1 | 2 | 3 | null
  limit?: number
  offset?: number
}

/** Everything the UI needs. Implemented by the Supabase backend and by the in-browser demo. */
export interface Api {
  mode: "live" | "demo"
  getProfile(): Promise<Profile | null>
  setProfile(name: string, linkedinUrl: string): Promise<Profile>
  importConnections(rows: ConnectionRow[], filename: string, onProgress?: (done: number) => void): Promise<number>
  listImports(): Promise<ImportRecord[]>
  searchNetwork(params: SearchParams): Promise<{ rows: NetworkPerson[]; total: number }>
  getPeople(ids: string[]): Promise<Person[]>
  pathGraph(targetId: string): Promise<PathEdge[]>
  egoGraph(): Promise<EgoGraph>
  stats(): Promise<Stats>
  listTargets(): Promise<Target[]>
  addTarget(personId: string, note?: string): Promise<void>
  removeTarget(personId: string): Promise<void>
  ensurePerson(p: { name: string; linkedinUrl?: string; company?: string; title?: string }): Promise<string>
  addLink(a: string, b: string, strength: Strength): Promise<void>
  setCloseness(personId: string, strength: Strength): Promise<void>
  resetData(): Promise<void>
}
