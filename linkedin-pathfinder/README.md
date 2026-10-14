# Pathfinder — warm intros, mapped

Find the warmest path to anyone on LinkedIn. Every user uploads their LinkedIn `Connections.csv`. Pathfinder joins those uploads into one shared network and tells each user **who to message first** to get introduced to the people they want to reach.

- **Frontend:** React 19 + TypeScript + Vite, Tailwind CSS v4, shadcn/ui (Radix), lucide icons, d3-force
- **Backend:** Supabase (Postgres + Auth). There is no separate server: all logic is SQL functions with row-level security.
- **Hosting:** any static host. `vercel.json` (Vercel) and `public/_redirects` (Netlify/Cloudflare Pages) are included.

Without Supabase credentials the site runs in **demo mode** with a fictional sample network. That means you can deploy it first and connect Supabase afterwards.

## How the shared network works

| Table | What it holds |
| --- | --- |
| `people` | One row per real person, matched by LinkedIn profile slug (`linkedin.com/in/<slug>`), or by name + company when there's no URL. |
| `profiles` | An app user, linked to the `people` row that represents them. |
| `edges` | "A knows B". **Import** edges come from CSV uploads and are shared with everyone. **Manual** edges are private notes that only affect their author's routes. |
| `targets`, `imports` | Per-user lists. |

When Alice uploads a CSV that contains Bob, and Bob later signs up with the same LinkedIn URL, Bob's account attaches to the node Alice's upload created. From then on, Bob's own uploads extend Alice's reach and the other way round.

**Pathfinding** (`path_graph`) runs a breadth-first search in Postgres and returns only the edges that lie on a shortest path from you to the target. The browser then lists every route in that set and ranks them by how close each relationship is. Closeness is what you set on your own 1st-degree connections: close, knows, or weak.

**Privacy.** RLS stops anyone from reading another user's edges. People only learn about a connection when it sits on one of their own shortest routes, much like LinkedIn's "mutual connections". This is a crowd-sourced graph, so someone could upload a fake CSV claiming they know a person. If that matters for your audience, add verification (for example, only count an edge once both sides have uploaded).

## Deploy

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com) (the free tier is fine).
2. Apply the schema. Either paste `supabase/migrations/20261014000000_network.sql` into **SQL Editor → New query → Run**, or use the CLI: `supabase link --project-ref <ref> && supabase db push`.
3. **Authentication → Sign In / Providers:** make sure Email is enabled (magic links).
4. **Authentication → URL Configuration:** set **Site URL** to your deployed URL (e.g. `https://pathfinder.vercel.app`). Add `https://pathfinder.vercel.app/**` and `http://localhost:5173/**` to **Redirect URLs**.
5. **Project Settings → API:** copy the Project URL and the publishable (or anon) key.

### 2. Vercel

1. **Add New → Project**, then import this repository.
2. Set **Root Directory** to `linkedin-pathfinder`. Vercel detects Vite automatically.
3. Add environment variables `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
4. Deploy. If you change env vars later, redeploy, because Vite inlines them at build time.

Netlify or Cloudflare Pages work the same way: base directory `linkedin-pathfinder`, build command `npm run build`, publish directory `dist`.

## Local development

```bash
cd linkedin-pathfinder
npm install
cp .env.example .env   # optional, leave empty for demo mode
npm run dev            # http://localhost:5173
npm test               # graph, routing, CSV and demo-backend tests
npm run lint && npm run build
```

Add more shadcn components with `npx shadcn@latest add <component>`. `components.json` is already configured.

## Using it

1. Sign in with a magic link and enter your LinkedIn profile URL.
2. **Import:** upload `Connections.csv` (LinkedIn → Settings → Data privacy → Get a copy of your data → Connections).
3. **Network:** browse everyone within three hops in a table or a graph, and mark how well you know your 1st-degree connections.
4. **Targets:** add people you want to reach. Each one gets the recommended route, a "next step", an editable intro request, alternative routes and a path map.
5. **⌘K / `/`** to search anyone. **G then O/T/N/I/S** jumps between pages.

## Project layout

```
src/
  app-context.tsx        auth session + picks the live (Supabase) or demo backend
  lib/api.ts             the backend interface the UI talks to
  lib/supabase.ts        Supabase implementation (RPC calls)
  lib/demo.ts            in-browser implementation with a seeded sample network
  lib/graph.ts           BFS degrees + shortest-path DAG (mirrors the SQL)
  lib/routes.ts          route ranking and intro message
  lib/csv.ts             LinkedIn Connections.csv parser
  components/ui/         shadcn/ui components
  components/            app shell, command menu, route chain, graphs, pickers
  pages/                 landing, login, onboarding, overview, targets, path, network, import, settings
supabase/migrations/     schema, RLS policies and RPC functions
```
