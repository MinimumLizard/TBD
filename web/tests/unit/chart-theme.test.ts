import { describe, expect, test } from "vitest";

import { paletteFrom, themed } from "@/lib/chart-theme";
import { lineOption } from "@/lib/charts";

describe("chart theme", () => {
  const dark: Record<string, string> = { "--text": "#e7edf6", "--muted": "#97a6bb", "--border": "#233149", "--surface": "#111b2c", "--accent": "#3cc6c0" };
  const p = paletteFrom((n) => dark[n] ?? "");

  test("takes the theme's tokens, with the light theme as fallback", () => {
    expect(p.text).toBe("#e7edf6");
    expect(p.series[0]).toBe("#3cc6c0");
    expect(p.series[1]).toBe("#e09f3e");
  });

  test("colours axes, labels and legend without touching the data", () => {
    const option = lineOption([{ name: "A", points: [["2026-10-01", 1]] }, { name: "B", points: [["2026-10-01", 2]] }], "%");
    const out = themed(option, p) as Record<string, any>;
    expect(out.series).toBe(option.series);
    expect(out.yAxis.axisLabel.color).toBe("#97a6bb");
    expect(out.yAxis.name).toBe("%");
    expect(out.legend.textStyle.color).toBe("#97a6bb");
    expect(out.color).toEqual(p.series);
  });
});
