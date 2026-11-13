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

/** Every address of the flow: the first question, each follow-up question, each path. */
export const START_PAGES = ["/start", ...PERSONAS.flatMap((p) => [`/start/${p.key}`, ...p.answers.map((a) => `/start/${p.key}/${a.key}`)])];

/** The home page tailored to each answer (app/home/[type]/[answer], lib/homes.ts). */
export const HOME_PAGES = PERSONAS.flatMap((p) => p.answers.map((a) => `/home/${p.key}/${a.key}`));

// What the visitor answered is remembered in one first-party cookie, set by the server when a path's page is opened
// (web/proxy.ts): "<type>.<answer>", or "skip" for a visitor who chose to go straight to the markets. The site's
// front door then opens on their own home page. It carries no identity and nothing about what they read.
export const START_COOKIE = "ziq-start";
export const SKIPPED = "skip";

export function readStart(value: string | null | undefined): { type: string; answer: string } | typeof SKIPPED | null {
  if (value === SKIPPED) return SKIPPED;
  const [type, key, ...rest] = (value ?? "").split(".");
  return rest.length === 0 && type && key && answer(type, key) ? { type, answer: key } : null;
}

/** The message key (start.tools.<key>) naming each page a step leads to. */
export const TOOL_KEYS: Record<string, string> = {
  "/markets": "markets", "/learn/savings": "savings", "/cse": "market", "/cse/shares": "shares", "/cse/shares/compare": "compare",
  "/cse/dealings": "dealings", "/bonds": "bonds", "/bonds/zscores": "zscores", "/bonds/carry": "carry",
};
