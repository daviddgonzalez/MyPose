import type { Person } from "./types"

export const roleLine = (p: Pick<Person, "title" | "company">) => [p.title, p.company].filter(Boolean).join(" · ")
