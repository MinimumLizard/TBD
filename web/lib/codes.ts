// "Cheat codes" (owner, 2026-11-26, decision 0027): public data most investors do not know is public, one tap away.
// Each points to a page that already exists; the tier is the one that shows it in full (config/entitlements.yaml
// decides what is actually shown, on the server; free visitors get a taste of each, as that file says). Text in
// messages (codes.<key>.title, codes.<key>.line).
import type { Tier } from "./registry";

export interface CheatCode {
  key: string;
  href: string;
  tier: Tier; // the tier that shows it in full
}

export const CODES: CheatCode[] = [
  { key: "dealings", href: "/cse/dealings", tier: "free" },
  { key: "flows", href: "/cse/dealings#flows", tier: "pro" },
  { key: "owners", href: "/search", tier: "free" }, // the top three free; the top 20 in Pro
  { key: "groups", href: "/search", tier: "pro" },
  { key: "totalReturn", href: "/cse/shares/compare", tier: "pro" },
  { key: "lab", href: "/cse/lab", tier: "pro" },
  { key: "fd", href: "/learn/savings", tier: "free" },
  { key: "bonds", href: "/bonds/zscores", tier: "plus" },
];

/** The codes for one company, as one search finds them: who owns it, what its directors did, the money flow. */
export function companyCodes(symbol: string): { key: string; href: string }[] {
  const share = `/cse/shares/${encodeURIComponent(symbol)}`;
  return [
    { key: "owners", href: `${share}#owners` },
    { key: "dealings", href: `${share}#dealings` },
    { key: "flows", href: "/cse/dealings#flows" },
  ];
}
