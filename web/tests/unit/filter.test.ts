import { describe, expect, it } from "vitest";

import { sectorGroup, sectorKey } from "@/lib/cse-display";
import { matchesQuery, param, searchText } from "@/lib/filter";

describe("finding things", () => {
  it("search text is lower case, without accents or punctuation", () => {
    expect(searchText("John Keells Holdings PLC", "JKH.N0000", null)).toBe("john keells holdings plc jkh.n0000");
    expect(searchText("Café  &  Co.")).toBe("cafe co.");
  });

  it("every word of the query must appear, in any order", () => {
    const text = searchText("John Keells Holdings PLC", "JKH.N0000", "Capital Goods");
    expect(matchesQuery(text, "keells")).toBe(true);
    expect(matchesQuery(text, "KEELLS john")).toBe(true);
    expect(matchesQuery(text, "jkh")).toBe(true);
    expect(matchesQuery(text, "keells bank")).toBe(false);
    expect(matchesQuery(text, "")).toBe(true);
    expect(matchesQuery(text, "   ")).toBe(true);
  });

  it("a query-string value is one bounded string", () => {
    expect(param(undefined)).toBe("");
    expect(param(["a", "b"])).toBe("a");
    expect(param("x".repeat(200))).toHaveLength(80);
  });
});

describe("sectors (the same rules as models/_lib/cse_sectors.py)", () => {
  it("normalises case, punctuation, spacing and GICS codes", () => {
    expect(sectorKey("45103010 - Application Software")).toBe("APPLICATIONSOFTWARE");
    expect(sectorGroup("X.N0000", "FOOD BEVERAGE & TOBACCO")).toBe("Food, Beverage & Tobacco");
    expect(sectorGroup("X.N0000", "Banks ")).toBe("Banks");
    expect(sectorGroup("X.N0000", "Capital Goods.")).toBe("Capital Goods");
    expect(sectorGroup("X.N0000", "Diversified Financial")).toBe("Diversified Financials");
    expect(sectorGroup("X.N0000", "- Property & Casualty Insurance")).toBe("Insurance");
    expect(sectorGroup("X.N0000", "45103010 - Application Software")).toBe("Software & Services");
  });

  it("the owner's assignment wins; unknown labels are unclassified", () => {
    expect(sectorGroup("MSL.N0000", "Services")).toBe("Transportation");
    expect(sectorGroup("X.N0000", "Services")).toBeNull();
    expect(sectorGroup("X.N0000", null)).toBeNull();
  });
});
