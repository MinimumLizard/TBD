// A sparkline drawn on the server as an SVG path (no script needed): the series scaled into a viewBox.

export interface Spark {
  line: string; // the path of the line
  area: string; // the same line closed down to the bottom, for a soft fill
  width: number;
  height: number;
}

export function sparkline(values: (number | null | undefined)[], width = 120, height = 32): Spark | null {
  const points = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (points.length < 2) return null;
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const pad = 2;
  const xy = points.map((v, i) => [
    (i / (points.length - 1)) * width,
    pad + (1 - (v - lo) / span) * (height - 2 * pad),
  ]);
  const f = (n: number) => Math.round(n * 10) / 10;
  const line = xy.map(([x, y], i) => `${i ? "L" : "M"}${f(x)} ${f(y)}`).join(" ");
  return { line, area: `${line} L${f(width)} ${height} L0 ${height} Z`, width, height };
}
