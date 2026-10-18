"use client";

// One charting library for the whole site: Apache ECharts (Apache-2.0). The option object is built on the server,
// after the tier check, so a chart can only ever show data the visitor is entitled to. It is also written into the
// page as data-chart, so the page's static copy (the owner's preview) can draw the same chart without this script.
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import { paletteFrom, themed } from "@/lib/chart-theme";

echarts.use([LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, DataZoomComponent, CanvasRenderer]);

export default function Chart({ option, label, height = 320 }: { option: Record<string, unknown>; label: string; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const style = getComputedStyle(document.documentElement);
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.setOption(themed(option, paletteFrom((n) => style.getPropertyValue(n))));
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [option]);
  return <div ref={ref} className="chart" style={{ height }} role="img" aria-label={label} data-chart={JSON.stringify(option)} />;
}
