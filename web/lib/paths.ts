// Starting paths (Janu's review, 2026-11-09; docs/plan-janu-review.md): the first thing a visitor is asked is where
// they are starting from, then one question that fits that answer (the share-account question goes only to people
// who have not started), and the answer leads to three steps: a guide, then the page of the site it explains. Paths
// choose what to read; they say nothing about what anyone should do with their money (hard rule 4). Every path is a
// plain address (/start/<type>/<answer>), so it works without JavaScript, can be shared, and is in the static
// preview. The text is in messages (start.*).

export interface Step {
  guide?: string; // a guide's slug (lib/guides.ts), or
  page?: string; // a page that teaches by itself (the savings comparison)
  tool?: string; // the page the step's guide explains: "then use it here"
}

export interface Answer {
  key: string;
  steps: [Step, Step, Step];
  stat?: "savers" | "investors" | "literacy";
}

export interface Persona {
  key: string;
  answers: Answer[];
}

export const PERSONAS: Persona[] = [
  {
    key: "new",
    answers: [
      { key: "deposits", stat: "savers", steps: [{ page: "/learn/savings" }, { guide: "markets-map", tool: "/markets" }, { guide: "getting-started", tool: "/bonds" }] },
      { key: "cash", stat: "literacy", steps: [{ guide: "getting-started", tool: "/learn/savings" }, { page: "/learn/savings" }, { guide: "markets-map", tool: "/markets" }] },
      { key: "assets", stat: "savers", steps: [{ guide: "markets-map", tool: "/markets" }, { page: "/learn/savings" }, { guide: "getting-started", tool: "/cse" }] },
    ],
  },
  {
    key: "curious",
    answers: [
      { key: "how", stat: "investors", steps: [{ guide: "getting-started", tool: "/learn/savings" }, { guide: "shares-basics", tool: "/cse/shares" }, { guide: "bonds-basics", tool: "/bonds" }] },
      { key: "risk", stat: "savers", steps: [{ guide: "diversification", tool: "/cse/shares" }, { page: "/learn/savings" }, { guide: "total-return", tool: "/cse/shares" }] },
      { key: "choose", stat: "investors", steps: [{ guide: "shares-basics", tool: "/cse" }, { guide: "company-figures", tool: "/cse/shares/compare" }, { guide: "yield-curve", tool: "/bonds" }] },
    ],
  },
  {
    key: "confused",
    answers: [
      { key: "returns", steps: [{ guide: "total-return", tool: "/cse/shares" }, { guide: "shares-basics", tool: "/cse" }, { guide: "diversification", tool: "/cse/shares/compare" }] },
      { key: "figures", steps: [{ guide: "company-figures", tool: "/cse/shares/compare" }, { guide: "ownership", tool: "/cse/shares" }, { guide: "directors-dealings", tool: "/cse/dealings" }] },
      { key: "bonds", steps: [{ guide: "bonds-basics", tool: "/bonds" }, { guide: "yield-curve", tool: "/bonds" }, { guide: "bond-relative-value", tool: "/bonds/zscores" }] },
      { key: "news", steps: [{ guide: "directors-dealings", tool: "/cse/dealings" }, { guide: "shares-basics", tool: "/cse" }, { guide: "money-flows", tool: "/cse/dealings" }] },
    ],
  },
  {
    key: "confident",
    answers: [
      { key: "shares", steps: [{ guide: "company-figures", tool: "/cse/shares/compare" }, { guide: "money-flows", tool: "/cse/dealings" }, { guide: "diversification", tool: "/cse/shares" }] },
      { key: "bonds", steps: [{ guide: "bond-relative-value", tool: "/bonds/zscores" }, { guide: "carry-rolldown", tool: "/bonds/carry" }, { guide: "duration-convexity", tool: "/bonds/carry" }] },
      { key: "both", steps: [{ guide: "company-figures", tool: "/cse/shares/compare" }, { guide: "bond-relative-value", tool: "/bonds/zscores" }, { guide: "markets-map", tool: "/markets" }] },
    ],
  },
];

export function persona(key: string): Persona | undefined {
  return PERSONAS.find((p) => p.key === key);
}

export function answer(personaKey: string, answerKey: string): Answer | undefined {
  return persona(personaKey)?.answers.find((a) => a.key === answerKey);
}

// Questions 3 and 4 (the owner, 2026-11-20): roughly how much, and when it might be needed. Both are optional. What
// they change is information only: costs at that amount, and what deposits and bills did over periods that long
// (components/YourMoney.tsx). They never change what a tier may see, and nothing is suggested.
export const AMOUNTS = ["lt100k", "lt1m", "lt10m", "gt10m"] as const;
export const HORIZONS = ["lt1y", "y1to3", "y3to5", "gt5y"] as const;
export type AmountKey = (typeof AMOUNTS)[number];
export type HorizonKey = (typeof HORIZONS)[number];
export const NOT_SAID = "na";

/** A typical amount for each band, used for worked examples of costs ("for example, on Rs 50,000"). */
export const EXAMPLE_AMOUNT: Record<AmountKey, number> = { lt100k: 50_000, lt1m: 500_000, lt10m: 5_000_000, gt10m: 20_000_000 };
/** The deposit and bill periods (lk_savings_compare's horizons, in years) that fit each timeframe. */
export const HORIZON_YEARS: Record<HorizonKey, number> = { lt1y: 1, y1to3: 3, y3to5: 5, gt5y: 10 };

export function isAmount(v: unknown): v is AmountKey {
  return typeof v === "string" && (AMOUNTS as readonly string[]).includes(v);
}

export function isHorizon(v: unknown): v is HorizonKey {
  return typeof v === "string" && (HORIZONS as readonly string[]).includes(v);
}

/** Every address of the flow: the first question, each follow-up question, the two optional questions, each path. */
export const START_PAGES = ["/start", ...PERSONAS.flatMap((p) => [
  `/start/${p.key}`, ...p.answers.flatMap((a) => [`/start/${p.key}/${a.key}/more`, `/start/${p.key}/${a.key}`]),
])];

/** The home page tailored to each answer (app/home/[type]/[answer], lib/homes.ts). */
export const HOME_PAGES = PERSONAS.flatMap((p) => p.answers.map((a) => `/home/${p.key}/${a.key}`));

// What the visitor answered is remembered in one first-party cookie, set by the server when a path's page is opened
// (web/proxy.ts): "<type>.<answer>", "<type>.<answer>.<amount>.<horizon>" (either may be "na"), or "skip" for a
// visitor who chose to go straight to the markets. The site's front door then opens on their own home page. It carries
// no identity and nothing about what they read.
export const START_COOKIE = "ziq-start";
export const SKIPPED = "skip";

export interface Started {
  type: string;
  answer: string;
  amount: AmountKey | null;
  horizon: HorizonKey | null;
}

export function readStart(value: string | null | undefined): Started | typeof SKIPPED | null {
  if (value === SKIPPED) return SKIPPED;
  const parts = (value ?? "").split(".");
  if (parts.length !== 2 && parts.length !== 4) return null;
  const [type, key, amount, horizon] = parts;
  if (!type || !key || !answer(type, key)) return null;
  if (parts.length === 4 && ((amount !== NOT_SAID && !isAmount(amount)) || (horizon !== NOT_SAID && !isHorizon(horizon)))) {
    return null;
  }
  return { type, answer: key, amount: isAmount(amount) ? amount : null, horizon: isHorizon(horizon) ? horizon : null };
}

export function writeStart(s: Started): string {
  return s.amount || s.horizon ? `${s.type}.${s.answer}.${s.amount ?? NOT_SAID}.${s.horizon ?? NOT_SAID}` : `${s.type}.${s.answer}`;
}

/** The message key (start.tools.<key>) naming each page a step leads to. */
export const TOOL_KEYS: Record<string, string> = {
  "/markets": "markets", "/learn/savings": "savings", "/cse": "market", "/cse/shares": "shares", "/cse/shares/compare": "compare",
  "/cse/dealings": "dealings", "/bonds": "bonds", "/bonds/zscores": "zscores", "/bonds/carry": "carry",
};
