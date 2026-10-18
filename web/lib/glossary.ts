// The terms the Learn page explains, in the order it shows them. Their text is in messages (learn.terms.<id>).
export const GLOSSARY = [
  "aspi", "spsl20", "turnover", "breadth", "foreign", "pe", "pbv", "dividendYield", "marketCap", "range52",
  "relative", "beta", "yield", "bp", "curve", "residual", "zscore", "liquidity", "bidOffer", "duration",
  "convexity", "carry", "rolldown", "methodVersion",
] as const;
export type GlossaryTerm = (typeof GLOSSARY)[number];
