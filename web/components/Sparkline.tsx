import { sparkline } from "@/lib/sparkline";

// A small trend line, drawn on the server (no script), for stat tiles.
export default function Sparkline({ values, label }: { values: (number | null)[]; label: string }) {
  const s = sparkline(values);
  if (!s) return null;
  return (
    <svg className="spark" viewBox={`0 0 ${s.width} ${s.height}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <path className="area" d={s.area} />
      <path className="line" d={s.line} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
