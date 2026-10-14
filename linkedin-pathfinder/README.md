# Intro Pathfinder

A small, self-contained website that tells you **who to message first** to get introduced to someone on LinkedIn.

Open `index.html` in a browser. No build step and no server. All data stays in your browser (localStorage); use **Export JSON** to back it up.

## How it works

LinkedIn shows each person's degree (1st / 2nd / 3rd / 3rd+), and for 2nd-degree people it lists your mutual connections. It does not expose the full chain for 3rd-degree people and has no public API for it, so the site combines:

1. **Your 1st-degree connections.** Import `Connections.csv` from LinkedIn's data export (Settings → Data privacy → Get a copy of your data → Connections).
2. **Targets.** Each target has the degree LinkedIn shows. For 2nd-degree targets, paste in the names from their "mutual connections" list.
3. **"Who knows whom" links.** For 3rd / 3rd+ targets, record bridge people, e.g. a coworker at the target's company who is 2nd-degree to you, and which of your connections knows them.

Each link (and each of your 1st-degree connections) has a strength: *close*, *knows*, or *weak*. The site runs a weighted shortest-path search (Dijkstra) from each target. Closer relationships cost less and every hop costs something, so it prefers short, warm chains. For each target it shows:

- the best chain (You → first contact → … → target)
- the person to message first and who to ask them to introduce you to
- a copy-ready intro request message
- alternative routes through your other connections
- tips on what to add when no route is known yet

**Load sample** fills in demo data so you can see it in action.
