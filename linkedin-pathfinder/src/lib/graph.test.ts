import { describe, expect, it } from "vitest"

import { parseConnectionsCsv } from "./csv"
import { createDemoApi } from "./demo"
import { buildAdjacency, degrees, shortestPathDag } from "./graph"
import { introMessage, rankRoutes } from "./routes"
import type { Person, Strength } from "./types"

const e = (a: string, b: string, strength: Strength = 2) => ({ a, b, strength })

describe("graph", () => {
  // me - bob - cara - gina ; me - dan - hank ; bob - hank ; me - eve (weak) - cara
  const adj = buildAdjacency([e("me", "bob", 3), e("bob", "cara"), e("cara", "gina"), e("me", "dan"), e("dan", "hank"), e("bob", "hank"), e("me", "eve", 1), e("eve", "cara", 3)])

  it("computes degrees and mutual counts", () => {
    const d = degrees(adj, "me")
    expect(d.get("bob")).toEqual({ degree: 1, mutuals: 0 })
    expect(d.get("cara")).toEqual({ degree: 2, mutuals: 2 })
    expect(d.get("hank")).toEqual({ degree: 2, mutuals: 2 })
    expect(d.get("gina")).toEqual({ degree: 3, mutuals: 1 })
  })

  it("keeps only edges on shortest paths", () => {
    const dag = shortestPathDag(adj, "me", "gina")
    expect(dag.map((x) => `${x.a}>${x.b}`).sort()).toEqual(["bob>cara", "cara>gina", "eve>cara", "me>bob", "me>eve"])
    expect(shortestPathDag(adj, "me", "nobody")).toEqual([])
  })

  it("ranks the warmest route first, one per first contact", () => {
    const routes = rankRoutes(shortestPathDag(adj, "me", "gina"), "me", "gina")
    expect(routes.map((r) => r.path.join(">"))).toEqual(["me>bob>cara>gina", "me>eve>cara>gina"])
    expect(routes[0].hops).toBe(3)
  })

  it("writes an intro request naming the next person", () => {
    const people = new Map<string, Person>(
      ["me", "bob", "cara", "gina"].map((id) => [id, { id, name: id[0].toUpperCase() + id.slice(1) + " X", company: "Co", title: "CEO", linkedin_url: null }])
    )
    const [r] = rankRoutes(shortestPathDag(adj, "me", "gina"), "me", "gina")
    expect(introMessage(r, people)).toMatch(/^Hi Bob, .*reach Gina X \(CEO at Co\).*Cara X knows them/)
  })
})

describe("csv", () => {
  it("parses LinkedIn's export with notes and quoted commas", () => {
    const csv = '﻿Notes:\n"When exporting your connection data, you may notice..."\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\nMaya,Chen,https://www.linkedin.com/in/maya,,"Stripe, Inc.",Engineer,01 Jan 2024\n,,,,,,\n'
    expect(parseConnectionsCsv(csv)).toEqual([{ name: "Maya Chen", url: "https://www.linkedin.com/in/maya", company: "Stripe, Inc.", title: "Engineer" }])
    expect(() => parseConnectionsCsv("a,b\n1,2")).toThrow(/header/)
  })
})

describe("demo api", () => {
  it("finds routes to every seeded target", async () => {
    const api = createDemoApi()
    const me = (await api.getProfile())!.person_id!
    for (const t of await api.listTargets()) {
      const routes = rankRoutes(await api.pathGraph(t.person.id), me, t.person.id)
      expect(routes.length, t.person.name).toBeGreaterThan(0)
    }
    const stats = await api.stats()
    expect(stats.first).toBeGreaterThan(0)
    expect(stats.third).toBeGreaterThan(0)
  })
})
