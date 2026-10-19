// The terms the Learn page explains, in the order it shows them. Their text is in messages (learn.terms.<id>).
export const GLOSSARY = [
  "aspi", "spsl20", "turnover", "breadth", "foreign", "pe", "pbv", "dividendYield", "exDate", "totalReturn",
  "marketCap", "range52", "directorsDealings", "relatedParty", "cluster",
  "relative", "beta", "yield", "bp", "curve", "residual", "zscore", "liquidity", "bidOffer", "duration",
  "convexity", "carry", "rolldown", "fixedDeposit", "awfdr", "treasuryBill", "inflation", "realReturn", "methodVersion",
] as const;
export type GlossaryTerm = (typeof GLOSSARY)[number];
