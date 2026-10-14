import type { Api } from "./api"
import { buildAdjacency, degrees, shortestPathDag } from "./graph"
import type { ImportRecord, NetworkPerson, Person, Profile, Strength, Target } from "./types"

// An in-browser stand-in for the Supabase backend, seeded with a fictional network.
// It follows the same rules as the SQL functions so the UI behaves identically.

interface Edge {
  a: string
  b: string
  by: string
  source: "import" | "manual"
  strength: Strength
}

const ME_USER = "demo-user"

const FIRST = ["Maya", "Raj", "Sam", "Priya", "Tom", "Alex", "Dana", "Jo", "Lena", "Marcus", "Aisha", "Diego", "Hannah", "Kenji", "Olivia", "Noah", "Zara", "Ethan", "Sofia", "Liam", "Grace", "Omar", "Chloe", "Felix", "Ines", "Victor", "Nora", "Theo", "Leila", "Ravi", "Emma", "Jonas", "Mei", "Caleb", "Amara", "Hugo", "Yara", "Isaac", "Tara", "Ben"]
const LAST = ["Chen", "Patel", "Ortiz", "Nair", "Becker", "Kim", "Wu", "Park", "Fischer", "Reed", "Khan", "Alvarez", "Lee", "Tanaka", "Brooks", "Silva", "Ahmed", "Novak", "Rossi", "Grant", "Hughes", "Haddad", "Laurent", "Meyer", "Costa", "Ivanova", "Byrne", "Moreau", "Sato", "Iyer"]
const COMPANIES = ["Northwind", "Lumen Labs", "Arcadia Health", "Vela Robotics", "Fieldstone Capital", "Halcyon AI", "Brightline", "Copperleaf", "Orbital Systems", "Meridian Bank", "Juniper Studio", "Atlas Freight"]
const TITLES = ["Software Engineer", "Product Manager", "Designer", "Data Scientist", "Recruiter", "Engineering Manager", "Founder", "Account Executive", "Research Scientist", "Marketing Lead", "Head of Talent", "VP Engineering"]

function rng(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296
    return seed / 4294967296
  }
}

function seed() {
  const rand = rng(42)
  const pick = <T,>(xs: T[]) => xs[Math.floor(rand() * xs.length)]
  const people = new Map<string, Person>()
  const used = new Set<string>()
  const mk = (name?: string, company?: string, title?: string): Person => {
    let n = name
    while (!n || used.has(n)) n = `${pick(FIRST)} ${pick(LAST)}`
    used.add(n)
    const id = `p${people.size + 1}`
    const slug = n.toLowerCase().replace(/\s+/g, "-")
    const p = { id, name: n, company: company ?? pick(COMPANIES), title: title ?? pick(TITLES), linkedin_url: `https://www.linkedin.com/in/${slug}` }
    people.set(id, p)
    return p
  }
  const edges: Edge[] = []
  const link = (x: Person, y: Person, by: string, strength: Strength = 2) => {
    if (x.id === y.id) return
    const [a, b] = x.id < y.id ? [x.id, y.id] : [y.id, x.id]
    if (!edges.some((e) => e.a === a && e.b === b && e.by === by)) edges.push({ a, b, by, source: "import", strength })
  }

  const me = mk("Jordan Avery", "Copperleaf", "Product Designer")
  const first = Array.from({ length: 28 }, () => mk())
  first.forEach((p, i) => link(me, p, ME_USER, ([3, 2, 2, 1] as Strength[])[i % 4]))

  // Some of your connections also use the app and uploaded their own networks.
  const members = first.slice(0, 6)
  const second: Person[] = []
  for (const m of members) {
    const theirs = Array.from({ length: 10 + Math.floor(rand() * 8) }, () => (rand() < 0.3 && second.length ? pick(second) : mk()))
    for (const p of theirs) {
      link(m, p, `u-${m.id}`)
      if (!second.includes(p)) second.push(p)
    }
    link(m, pick(first), `u-${m.id}`)
  }
  // A few 2nd-degree people are members too, which reveals 3rd-degree people.
  for (const m of second.slice(0, 4)) {
    for (let i = 0; i < 8; i++) link(m, mk(), `u-${m.id}`)
  }

  // Named targets so the demo has interesting routes.
  const priya = mk("Priya Raman", "Halcyon AI", "Head of Talent")
  link(members[0], priya, `u-${members[0].id}`)
  link(members[2], priya, `u-${members[2].id}`)
  const dana = mk("Dana Whitfield", "Vela Robotics", "VP Engineering")
  link(second[3], dana, `u-${second[3].id}`)
  const marcus = mk("Marcus Bell", "Fieldstone Capital", "Partner")
  link(second[1], marcus, `u-${second[1].id}`)
  link(second[2], marcus, `u-${second[2].id}`)

  const targets: { personId: string; note: string | null; created_at: string }[] = [
    { personId: priya.id, note: "Ask about the design systems role", created_at: new Date(Date.now() - 864e5).toISOString() },
    { personId: dana.id, note: null, created_at: new Date(Date.now() - 3 * 864e5).toISOString() },
    { personId: marcus.id, note: "Seed round intro", created_at: new Date(Date.now() - 6 * 864e5).toISOString() },
  ]
  const imports: ImportRecord[] = [{ id: 1, filename: "Connections.csv", row_count: first.length, created_at: new Date(Date.now() - 9 * 864e5).toISOString() }]
  return { people, edges, me, targets, imports, memberCount: members.length + 5 }
}

const keyOf = (name: string, url?: string | null, company?: string | null) => {
  const slug = url?.match(/linkedin\.com\/in\/([^/?#]+)/i)?.[1]
  return slug ? `li:${slug.toLowerCase()}` : `nm:${name.trim().toLowerCase()}|${(company ?? "").trim().toLowerCase()}`
}

const STORE = "pf-demo-state"

function load(): ReturnType<typeof seed> {
  try {
    const raw = sessionStorage.getItem(STORE)
    if (raw) {
      const v = JSON.parse(raw)
      return { ...v, people: new Map(v.people) }
    }
  } catch {
    /* fall through to a fresh seed */
  }
  return seed()
}

export function createDemoApi(): Api {
  const s = load()
  // Keep demo edits across page reloads within the tab.
  const persist = () => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify({ ...s, people: [...s.people] }))
    } catch {
      /* storage unavailable */
    }
  }
  const profile: Profile = { id: ME_USER, person_id: s.me.id, full_name: s.me.name, linkedin_url: s.me.linkedin_url }
  const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 120))
  const save = <T,>(v: T) => (persist(), delay(v))
  const adj = () => buildAdjacency(s.edges.filter((e) => e.source === "import" || e.by === ME_USER))

  const upsert = (name: string, url?: string, company?: string, title?: string) => {
    const k = keyOf(name, url, company)
    const found = [...s.people.values()].find((p) => keyOf(p.name, p.linkedin_url, p.company) === k)
    if (found) return found
    const p: Person = { id: `p${s.people.size + 1}`, name: name.trim(), company: company || null, title: title || null, linkedin_url: url || null }
    s.people.set(p.id, p)
    return p
  }
  const myEdge = (other: string) => {
    const [a, b] = s.me.id < other ? [s.me.id, other] : [other, s.me.id]
    return s.edges.find((e) => e.a === a && e.b === b && e.by === ME_USER)
  }
  const addEdge = (x: string, y: string, source: Edge["source"], strength: Strength) => {
    const [a, b] = x < y ? [x, y] : [y, x]
    const ex = s.edges.find((e) => e.a === a && e.b === b && e.by === ME_USER)
    if (ex) ex.strength = strength
    else s.edges.push({ a, b, by: ME_USER, source, strength })
  }

  return {
    mode: "demo",
    getProfile: () => delay(profile),
    async setProfile(name) {
      profile.full_name = name
      s.me.name = name
      s.people.get(s.me.id)!.name = name
      return save(profile)
    },
    async importConnections(rows, filename, onProgress) {
      for (const r of rows) {
        const p = upsert(r.name, r.url, r.company, r.title)
        if (p.id !== s.me.id && !myEdge(p.id)) addEdge(s.me.id, p.id, "import", 2)
      }
      onProgress?.(rows.length)
      s.imports.unshift({ id: s.imports.length + 1, filename, row_count: rows.length, created_at: new Date().toISOString() })
      return save(rows.length)
    },
    listImports: () => delay([...s.imports]),
    async searchNetwork({ query, degree, limit = 50, offset = 0 }) {
      const deg = degrees(adj(), s.me.id)
      const q = query?.trim().toLowerCase()
      const rows: NetworkPerson[] = [...s.people.values()]
        .filter((p) => p.id !== s.me.id)
        .map((p) => {
          const d = deg.get(p.id)
          return { ...p, degree: d?.degree ?? null, mutuals: d?.mutuals ?? null, closeness: d?.degree === 1 ? (myEdge(p.id)?.strength ?? 2) : null }
        })
        .filter((p) => (q ? `${p.name} ${p.company ?? ""}`.toLowerCase().includes(q) : p.degree !== null))
        .filter((p) => !degree || p.degree === degree)
        .sort((a, b) => (a.degree ?? 9) - (b.degree ?? 9) || (b.mutuals ?? 0) - (a.mutuals ?? 0) || a.name.localeCompare(b.name))
      return delay({ rows: rows.slice(offset, offset + limit), total: rows.length })
    },
    getPeople: (ids) => delay(ids.map((id) => s.people.get(id)).filter((p): p is Person => !!p)),
    pathGraph: (targetId) => delay(shortestPathDag(adj(), s.me.id, targetId)),
    async egoGraph() {
      const deg = degrees(adj(), s.me.id)
      const ids = new Set([s.me.id, ...[...deg].filter(([, d]) => d.degree <= 2).map(([id]) => id)])
      const a = adj()
      const links: { source: string; target: string }[] = []
      for (const id of ids) for (const n of a.get(id)?.keys() ?? []) if (ids.has(n) && id < n) links.push({ source: id, target: n })
      const nodes = [...ids].map((id) => {
        const p = s.people.get(id)!
        return { id, name: p.name, company: p.company, title: p.title, degree: (id === s.me.id ? 0 : deg.get(id)!.degree) as 0 | 1 | 2 }
      })
      return delay({ nodes, links })
    },
    async stats() {
      const deg = [...degrees(adj(), s.me.id).values()]
      const n = (d: number) => deg.filter((x) => x.degree === d).length
      return delay({ first: n(1), second: n(2), third: n(3), members: s.memberCount, people: s.people.size, targets: s.targets.length })
    },
    listTargets: () =>
      delay(s.targets.map((t): Target => ({ person: s.people.get(t.personId)!, note: t.note, created_at: t.created_at }))),
    async addTarget(personId, note) {
      if (!s.targets.some((t) => t.personId === personId)) s.targets.unshift({ personId, note: note || null, created_at: new Date().toISOString() })
      return save(undefined)
    },
    async removeTarget(personId) {
      s.targets = s.targets.filter((t) => t.personId !== personId)
      return save(undefined)
    },
    async ensurePerson({ name, linkedinUrl, company, title }) {
      return save(upsert(name, linkedinUrl, company, title).id)
    },
    async addLink(x, y, strength) {
      if (x !== y) addEdge(x, y, "manual", strength)
      return save(undefined)
    },
    async setCloseness(personId, strength) {
      addEdge(s.me.id, personId, myEdge(personId)?.source ?? "manual", strength)
      return save(undefined)
    },
    async resetData() {
      s.edges = s.edges.filter((e) => e.by !== ME_USER)
      s.targets = []
      s.imports = []
      return save(undefined)
    },
  }
}
