// Starting paths (lib/paths.ts): every answer leads to three steps that exist, every page a step names is a page of
// the site with a label, every question and answer has its text, and every address of the flow is visited by the
// tier-leak tests.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GUIDE_SLUGS } from "@/lib/guides";
import { AMOUNTS, HORIZONS, HORIZON_YEARS, PERSONAS, START_PAGES, TOOL_KEYS, answer, persona } from "@/lib/paths";
import { ALL_PAGES } from "@/lib/routes";

const messages = JSON.parse(readFileSync(join(__dirname, "../../messages/en.json"), "utf8"));
const start = messages.start;

describe("starting paths", () => {
  it("has four starting points, each with its text and a follow-up question", () => {
    expect(PERSONAS.map((p) => p.key)).toEqual(["new", "curious", "confused", "confident"]);
    for (const p of PERSONAS) {
      for (const k of ["title", "desc", "short"]) expect(typeof start.types[p.key][k], `${p.key}.${k}`).toBe("string");
      expect(typeof start.questions[p.key].question).toBe("string");
      expect(typeof start.result.intro[p.key]).toBe("string");
      expect(p.answers.length).toBeGreaterThanOrEqual(3);
      expect(new Set(p.answers.map((a) => a.key)).size).toBe(p.answers.length);
    }
  });

  it("every answer has its text, a reason and three steps that lead somewhere real", () => {
    for (const p of PERSONAS) {
      for (const a of p.answers) {
        const where = `${p.key}/${a.key}`;
        expect(typeof start.questions[p.key][a.key], where).toBe("string");
        expect(typeof start.result.why[a.key], where).toBe("string");
        expect(a.steps).toHaveLength(3);
        for (const s of a.steps) {
          expect(Boolean(s.guide) !== Boolean(s.page), `${where}: a step is a guide or a page`).toBe(true);
          if (s.guide) expect(GUIDE_SLUGS, where).toContain(s.guide);
          for (const href of [s.page, s.tool].filter(Boolean) as string[]) {
            expect(ALL_PAGES, `${where} -> ${href}`).toContain(href);
            expect(typeof start.tools[TOOL_KEYS[href]], `${where} -> ${href}`).toBe("string");
          }
        }
        if (a.stat) expect(start.stats[a.stat], where).toBeDefined();
      }
    }
  });

  it("the share-account question reaches only people who have not started", () => {
    const guidesOf = (k: string) => persona(k)!.answers.flatMap((a) => a.steps.map((s) => s.guide));
    expect(guidesOf("confused")).not.toContain("getting-started");
    expect(guidesOf("confident")).not.toContain("getting-started");
    expect(guidesOf("new")).toContain("getting-started");
  });

  it("every address of the flow is a page the leak tests visit, and unknown ones are not paths", () => {
    expect(START_PAGES).toHaveLength(1 + PERSONAS.length + 2 * PERSONAS.reduce((n, p) => n + p.answers.length, 0));
    for (const url of START_PAGES) expect(ALL_PAGES).toContain(url);
    expect(answer("new", "shares")).toBeUndefined();
    expect(answer("nobody", "cash")).toBeUndefined();
    expect(answer("new", "cash")?.steps[0].guide).toBe("getting-started");
  });

  it("each statistic has its value, label and source", () => {
    for (const k of ["investors", "literacy", "savers"]) {
      for (const f of ["value", "label", "source"]) expect(typeof start.stats[k][f], `${k}.${f}`).toBe("string");
    }
  });
});

describe("questions 3 and 4", () => {
  it("every amount and timeframe has its text, and every money sentence exists", () => {
    for (const a of AMOUNTS) expect(typeof start.amounts[a], a).toBe("string");
    for (const h of HORIZONS) {
      expect(typeof start.horizons[h], h).toBe("string");
      expect([1, 3, 5, 10]).toContain(HORIZON_YEARS[h]);           // lk_savings_compare's horizons
    }
    for (const k of ["title", "lead", "amountQuestion", "horizonQuestion", "submit", "skip"]) {
      expect(typeof start.more[k], k).toBe("string");
    }
    for (const k of ["cost", "spread", "insured", "fd", "bill", "worst", "shares", "note"]) {
      expect(typeof messages.money[k], k).toBe("string");
    }
  });
});
