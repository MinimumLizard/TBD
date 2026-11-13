// The front door and the tailored home pages (decision 0025): every answer has a home whose guides and pages exist,
// the cookie is read strictly, and every home is a page the tier-leak tests visit.
import { describe, expect, it } from "vitest";

import { GUIDE_SLUGS } from "@/lib/guides";
import { HOME_TYPES, home } from "@/lib/homes";
import { MENUS } from "@/lib/menu";
import { HOME_PAGES, PERSONAS, SKIPPED, readStart } from "@/lib/paths";
import { ALL_PAGES } from "@/lib/routes";

describe("tailored home pages", () => {
  it("every starting type has a home, and every answer's home leads to guides and pages that exist", () => {
    expect(HOME_TYPES.sort()).toEqual(PERSONAS.map((p) => p.key).sort());
    const menuPages = MENUS.flatMap((m) => m.items.map((i) => i.href));
    for (const p of PERSONAS) {
      for (const a of p.answers) {
        const h = home(p.key, a.key)!;
        const where = `${p.key}/${a.key}`;
        expect(h.blocks.length, where).toBeGreaterThan(1);
        expect(new Set(h.blocks).size, where).toBe(h.blocks.length);
        expect(h.guides.length, where).toBeGreaterThan(0);
        for (const g of h.guides) {
          expect(GUIDE_SLUGS, where).toContain(g);
          expect(a.steps.map((s) => s.guide), `${where}: a guide of the path is not repeated`).not.toContain(g);
        }
        for (const href of h.tools) {
          expect(menuPages, `${where} -> ${href}`).toContain(href);
          expect(ALL_PAGES, `${where} -> ${href}`).toContain(href);
        }
      }
    }
  });

  it("an answer changes the mix where it should, and unknown answers have no home", () => {
    expect(home("confident", "bonds")!.blocks[0]).toBe("yieldTiles");
    expect(home("confident", "shares")!.blocks[0]).toBe("shareTiles");
    expect(home("new", "cash")!.blocks[0]).toBe("savings");
    expect(home("new", "bonds")).toBeUndefined();
    expect(home("nobody", "cash")).toBeUndefined();
  });

  it("a newcomer's home shows no yield-curve chart, and only homes of investors show the full tiles", () => {
    for (const a of PERSONAS.find((p) => p.key === "new")!.answers) {
      const blocks = home("new", a.key)!.blocks;
      for (const b of ["curve", "charts", "tiles", "yieldTiles"]) expect(blocks).not.toContain(b);
    }
  });

  it("every home is a page the leak tests visit", () => {
    expect(HOME_PAGES).toHaveLength(PERSONAS.reduce((n, p) => n + p.answers.length, 0));
    for (const url of HOME_PAGES) expect(ALL_PAGES).toContain(url);
    for (const url of ["/", "/markets", "/privacy", "/signup/thanks"]) expect(ALL_PAGES).toContain(url);
  });
});

describe("the starting cookie", () => {
  it("is read only when it names a real answer, or the skip", () => {
    expect(readStart("curious.how")).toEqual({ type: "curious", answer: "how" });
    expect(readStart(SKIPPED)).toBe(SKIPPED);
    for (const bad of [undefined, null, "", "curious", "curious.", "curious.nothing", "nobody.how", "curious.how.more",
                       "../etc", "curious.how/../../x", "CURIOUS.HOW"]) {
      expect(readStart(bad), String(bad)).toBeNull();
    }
  });
});
