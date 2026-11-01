// The Learn section's guides and the site's menus: every guide and menu entry has its text, every link it makes goes
// to a page the site has, and guides are listed by level in reading order.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GUIDES, GUIDE_SLUGS, LEVELS, LEVEL_OF_TIER, guide, neighbours } from "@/lib/guides";
import { MENUS } from "@/lib/menu";
import { ALL_PAGES } from "@/lib/routes";
import { TIERS } from "@/lib/registry";

const messages = JSON.parse(readFileSync(join(__dirname, "../../messages/en.json"), "utf8"));

describe("guides", () => {
  it("every guide has its title, summary, key points, sections and limits", () => {
    for (const g of GUIDES) {
      const m = messages.guides[g.slug];
      expect(m, g.slug).toBeDefined();
      expect(typeof m.title).toBe("string");
      expect(typeof m.summary).toBe("string");
      expect(m.keypoints.length).toBeGreaterThan(1);
      expect(m.limits.length).toBeGreaterThan(0);
      expect(m.sections.length).toBeGreaterThan(1);
      for (const s of m.sections) {
        expect(typeof s.h).toBe("string");
        expect(s.p.length).toBeGreaterThan(0);
      }
    }
  });

  it("slugs are unique and every guide is a page the leak tests visit", () => {
    expect(new Set(GUIDE_SLUGS).size).toBe(GUIDE_SLUGS.length);
    for (const slug of GUIDE_SLUGS) expect(ALL_PAGES).toContain(`/learn/${slug}`);
  });

  it("every tool a guide links to is a page of the site with a label", () => {
    for (const g of GUIDES) {
      for (const tool of g.tools) {
        expect(ALL_PAGES, `${g.slug} -> ${tool.href}`).toContain(tool.href.split("#")[0]);
        expect(typeof messages.guides.tools[tool.key], tool.key).toBe("string");
      }
    }
  });

  it("guides are grouped by level, in the levels' order, and every level has text", () => {
    const order = GUIDES.map((g) => LEVELS.indexOf(g.level));
    expect(order).toEqual([...order].sort((a, b) => a - b));
    for (const level of LEVELS) {
      expect(GUIDES.some((g) => g.level === level)).toBe(true);
      expect(typeof messages.guides.levels[level].title).toBe("string");
    }
    for (const tier of TIERS) expect(LEVEL_OF_TIER).toHaveProperty(tier);
  });

  it("neighbours follow the reading order", () => {
    expect(neighbours(GUIDES[0].slug).prev).toBeNull();
    expect(neighbours(GUIDES[1].slug).prev?.slug).toBe(GUIDES[0].slug);
    expect(neighbours(GUIDES[GUIDES.length - 1].slug).next).toBeNull();
    expect(guide("no-such-guide")).toBeUndefined();
  });
});

describe("menus", () => {
  it("every menu entry has a title and description and goes to a page of the site", () => {
    for (const menu of MENUS) {
      expect(typeof messages.menu[menu.key].label).toBe("string");
      for (const item of menu.items) {
        expect(typeof messages.menu[menu.key][item.key].title, `${menu.key}.${item.key}`).toBe("string");
        expect(typeof messages.menu[menu.key][item.key].desc, `${menu.key}.${item.key}`).toBe("string");
        expect(ALL_PAGES).toContain(item.href);
      }
    }
  });
});
