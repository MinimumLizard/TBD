// The Learn section's guides (docs/research/retail-investor-needs-2026-11.md §5): plain-language explanations at three
// levels that match the tiers' tools. Every guide is free to read; a guide's level says which tier's tools it
// explains. Each guide's text is in messages (guides.<slug>), and each links to the pages it explains.
import type { Tier } from "./registry";

export type Level = "basics" | "deeper" | "advanced";

export const LEVELS: Level[] = ["basics", "deeper", "advanced"];

export const LEVEL_OF_TIER: Record<Tier, Level | null> = { free: "basics", plus: "deeper", pro: "advanced", professional: null };

export interface Guide {
  slug: string;
  level: Level;
  minutes: number;
  tools: { href: string; key: string }[]; // the pages this guide explains; key names the link in messages (ui.tools.<key>)
}

export const GUIDES: Guide[] = [
  { slug: "markets-map", level: "basics", minutes: 5, tools: [{ href: "/", key: "home" }, { href: "/learn/savings", key: "savings" }] },
  { slug: "shares-basics", level: "basics", minutes: 7, tools: [{ href: "/cse", key: "market" }, { href: "/cse/shares", key: "shares" }] },
  { slug: "total-return", level: "basics", minutes: 5, tools: [{ href: "/cse/shares", key: "shares" }] },
  { slug: "company-figures", level: "basics", minutes: 6, tools: [{ href: "/cse/shares", key: "shares" }] },
  { slug: "ownership", level: "basics", minutes: 5, tools: [{ href: "/cse/shares", key: "shares" }] },
  { slug: "directors-dealings", level: "basics", minutes: 5, tools: [{ href: "/cse/dealings", key: "dealings" }] },
  { slug: "bonds-basics", level: "basics", minutes: 7, tools: [{ href: "/bonds", key: "bonds" }, { href: "/learn/savings", key: "savings" }] },
  { slug: "yield-curve", level: "basics", minutes: 6, tools: [{ href: "/bonds", key: "bonds" }] },
  { slug: "bond-relative-value", level: "deeper", minutes: 6, tools: [{ href: "/bonds/zscores", key: "zscores" }, { href: "/bonds", key: "bonds" }] },
  { slug: "trades-vs-quotes", level: "deeper", minutes: 5, tools: [{ href: "/bonds/execution", key: "execution" }] },
  { slug: "money-flows", level: "deeper", minutes: 5, tools: [{ href: "/cse/dealings#flows", key: "flows" }] },
  { slug: "diversification", level: "deeper", minutes: 6, tools: [{ href: "/cse/shares", key: "shares" }] },
  { slug: "carry-rolldown", level: "advanced", minutes: 6, tools: [{ href: "/bonds/carry", key: "carry" }] },
  { slug: "duration-convexity", level: "advanced", minutes: 6, tools: [{ href: "/bonds/carry", key: "carry" }] },
];

export const GUIDE_SLUGS = GUIDES.map((g) => g.slug);

export function guide(slug: string): Guide | undefined {
  return GUIDES.find((g) => g.slug === slug);
}

/** The guide before and after this one, in reading order. */
export function neighbours(slug: string): { prev: Guide | null; next: Guide | null } {
  const i = GUIDES.findIndex((g) => g.slug === slug);
  return { prev: i > 0 ? GUIDES[i - 1] : null, next: i >= 0 && i < GUIDES.length - 1 ? GUIDES[i + 1] : null };
}
