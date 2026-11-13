// The home page tailored to what a visitor answered (decision 0025; app/home/[type]/[answer]). Each starting type
// gets the blocks that fit it, in order, with the guides and pages that go with them; a few answers change the mix
// (someone who follows bonds sees the yield curve first). The blocks show the same free figures as the markets page:
// tailoring chooses what is shown first, never what a tier may see (lib/entitlements.ts decides that, as everywhere).
import { answer } from "./paths";

export type Block =
  | "savings" // what deposits and bills pay today, next to inflation
  | "brief" // the day in a few sentences
  | "tiles" // the share market's and the yield curve's main figures
  | "shareTiles"
  | "yieldTiles"
  | "shares" // the ASPI's year
  | "curve" // today's yield curve
  | "charts" // both charts side by side
  | "lookup"; // a search box for a share, a bond or a term

export interface Home {
  blocks: Block[];
  guides: string[]; // lib/guides.ts slugs, beyond the path's own three steps
  tools: string[]; // pages of the site (lib/menu.ts)
}

const BY_TYPE: Record<string, Home> = {
  new: {
    blocks: ["savings", "brief"],
    guides: ["getting-started", "markets-map", "bonds-basics", "shares-basics"],
    tools: ["/learn/savings", "/learn/glossary", "/bonds"],
  },
  curious: {
    blocks: ["brief", "savings", "shares"],
    guides: ["getting-started", "shares-basics", "bonds-basics", "total-return"],
    tools: ["/cse", "/cse/shares", "/bonds", "/learn/savings"],
  },
  confused: {
    blocks: ["brief", "tiles", "lookup"],
    guides: ["total-return", "company-figures", "directors-dealings", "yield-curve"],
    tools: ["/cse/shares/compare", "/cse/dealings", "/bonds", "/learn/glossary"],
  },
  confident: {
    blocks: ["tiles", "charts", "brief"],
    guides: ["bond-relative-value", "money-flows", "carry-rolldown", "diversification"],
    tools: ["/cse/shares/compare", "/cse/dealings", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/methods"],
  },
};

const BY_ANSWER: Record<string, Partial<Home>> = {
  "curious.risk": { guides: ["diversification", "total-return", "getting-started", "bonds-basics"] },
  "confused.bonds": {
    blocks: ["brief", "yieldTiles", "curve", "lookup"],
    guides: ["bonds-basics", "yield-curve", "bond-relative-value", "trades-vs-quotes"],
    tools: ["/bonds", "/learn/savings", "/bonds/zscores", "/learn/glossary"],
  },
  "confident.shares": {
    blocks: ["shareTiles", "shares", "brief", "lookup"],
    guides: ["company-figures", "money-flows", "diversification", "ownership"],
    tools: ["/cse/shares/compare", "/cse/dealings", "/cse", "/cse/shares", "/methods"],
  },
  "confident.bonds": {
    blocks: ["yieldTiles", "curve", "brief"],
    guides: ["bond-relative-value", "carry-rolldown", "duration-convexity", "trades-vs-quotes"],
    tools: ["/bonds", "/bonds/zscores", "/bonds/execution", "/bonds/carry", "/methods"],
  },
};

/** The home of one answer, or undefined when the type or answer is not one of the starting paths. */
export function home(type: string, key: string): Home | undefined {
  const a = answer(type, key);
  if (!a) return undefined;
  const h = { ...BY_TYPE[type], ...BY_ANSWER[`${type}.${key}`] };
  const own = new Set(a.steps.map((s) => s.guide));
  return { ...h, guides: h.guides.filter((g) => !own.has(g)).slice(0, 3) };
}

export const HOME_TYPES = Object.keys(BY_TYPE);
