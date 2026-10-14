export type Degree = 1 | 2 | 3
/** How well two people know each other: 1 = weak, 2 = know each other, 3 = close. */
export type Strength = 1 | 2 | 3

export interface Person {
  id: string
  name: string
  company: string | null
  title: string | null
  linkedin_url: string | null
}

export interface NetworkPerson extends Person {
  /** Your degree to this person, or null when they aren't within three hops. */
  degree: Degree | null
  /** For 2nd/3rd degree: how many people one hop closer to you know them. */
  mutuals: number | null
  /** For 1st degree: how well you know them. */
  closeness: Strength | null
}

export interface Profile {
  id: string
  person_id: string | null
  full_name: string | null
  linkedin_url: string | null
}

/** An edge on a shortest path; `hop` is how far `a` is from you. */
export interface PathEdge {
  a: string
  b: string
  strength: Strength
  hop: number
}

export interface Stats {
  first: number
  second: number
  third: number
  members: number
  people: number
  targets: number
}

export interface Target {
  person: Person
  note: string | null
  created_at: string
}

export interface ImportRecord {
  id: number
  filename: string | null
  row_count: number
  created_at: string
}

export interface EgoGraph {
  nodes: { id: string; name: string; company: string | null; title: string | null; degree: 0 | 1 | 2 }[]
  links: { source: string; target: string }[]
}

export interface ConnectionRow {
  name: string
  url: string
  company: string
  title: string
}
