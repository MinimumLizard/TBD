// ECharts option builders. Plain data only (no functions), so options can be built on the server and handed to the
// client Chart component after the tier check.

// The legend stays on one line above the plot (scrolling sideways on a phone), and the plot starts below both the
// legend and the y-axis name, so neither ever covers the data.
const LEGEND = { type: "scroll", top: 0 };
const TOP_WITH_LEGEND = 56;

export function lineOption(series: { name: string; points: [string, number | null][] }[], yName?: string) {
  return {
    animation: false,
    tooltip: { trigger: "axis" },
    legend: series.length > 1 ? LEGEND : undefined,
    grid: { left: 48, right: 16, top: series.length > 1 ? TOP_WITH_LEGEND : yName ? 32 : 16, bottom: 32 },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true, name: yName },
    series: series.map((s) => ({ name: s.name, type: "line", showSymbol: false, data: s.points })),
  };
}

export function curveOption(args: {
  quotes: [number, number, string][];
  wide?: [number, number, string][];
  trades: [number, number, string][];
  curve: [number, number][];
  names: { quotes: string; wide?: string; trades: string; curve: string; years: string; yield: string };
}) {
  return {
    animation: false,
    tooltip: { trigger: "item" },
    legend: LEGEND,
    grid: { left: 48, right: 16, top: TOP_WITH_LEGEND, bottom: 40 },
    xAxis: { type: "value", name: args.names.years, nameLocation: "middle", nameGap: 26, min: 0 },
    yAxis: { type: "value", name: args.names.yield, scale: true },
    series: [
      { name: args.names.quotes, type: "scatter", symbolSize: 6, data: args.quotes },
      ...(args.wide && args.wide.length
        ? [{ name: args.names.wide, type: "scatter", symbol: "emptyCircle", symbolSize: 6, data: args.wide }]
        : []),
      { name: args.names.trades, type: "scatter", symbol: "diamond", symbolSize: 9, data: args.trades },
      { name: args.names.curve, type: "line", showSymbol: false, smooth: true, data: args.curve },
    ],
  };
}

/** Quotes whose weight in the fit is under this (relative to an average quote of 1) are drawn apart: in practice the
 * wide, administered quotes, which version 2 of the curve includes at a tiny weight (decision 0014). */
export const LOW_WEIGHT = 0.1;

/** Points along the fitted curve, from the shortest to the longest maturity quoted. */
export function curvePoints(fit: { beta0: number; beta1: number; beta2: number; lambda_years: number }, maxTau: number): [number, number][] {
  const end = Math.max(1, Math.ceil(maxTau));
  return Array.from({ length: end * 4 }, (_, i) => {
    const tau = 0.1 + (i * (end - 0.1)) / (end * 4 - 1);
    return [tau, nelsonSiegel(tau, fit.beta0, fit.beta1, fit.beta2, fit.lambda_years)] as [number, number];
  });
}

/** The Nelson-Siegel curve at maturities tau (years), as the model defines it. */
export function nelsonSiegel(tau: number, b0: number, b1: number, b2: number, lambda: number): number {
  const x = tau / lambda;
  const slope = x > 1e-8 ? (1 - Math.exp(-x)) / x : 1;
  return b0 + b1 * slope + b2 * (slope - Math.exp(-x));
}
