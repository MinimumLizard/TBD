// The site's menus, grouped by market. Each entry's title and one-line description are in messages (menu.<key>);
// the tier is shown next to a page whose main content is part of a paid tier (config/entitlements.yaml decides
// what is actually shown: this only labels the menu).
import type { Tier } from "./registry";

export interface MenuItem {
  key: string;
  href: string;
  tier?: Tier;
}

export interface Menu {
  key: string;
  items: MenuItem[];
}

export const MENUS: Menu[] = [
  {
    key: "shares",
    items: [
      { key: "market", href: "/cse" },
      { key: "allShares", href: "/cse/shares" },
      { key: "compare", href: "/cse/shares/compare" },
      { key: "dealings", href: "/cse/dealings" },
    ],
  },
  {
    key: "bonds",
    items: [
      { key: "curve", href: "/bonds" },
      { key: "zscores", href: "/bonds/zscores", tier: "plus" },
      { key: "execution", href: "/bonds/execution", tier: "plus" },
      { key: "carry", href: "/bonds/carry", tier: "pro" },
    ],
  },
  {
    key: "savings",
    items: [{ key: "savings", href: "/learn/savings" }],
  },
  {
    key: "learn",
    items: [
      { key: "guides", href: "/learn" },
      { key: "glossary", href: "/learn/glossary" },
      { key: "methods", href: "/methods" },
      { key: "about", href: "/about" },
    ],
  },
];
