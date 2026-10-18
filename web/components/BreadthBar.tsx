import { int } from "@/lib/format";

// How many shares rose, did not change, and fell: one bar, three colours, with the counts underneath.
export default function BreadthBar({ up, flat, down, labels }: {
  up: number | null;
  flat: number | null;
  down: number | null;
  labels: { up: string; flat: string; down: string };
}) {
  const u = up ?? 0, f = flat ?? 0, d = down ?? 0;
  const total = u + f + d;
  if (!total) return null;
  const w = (n: number) => `${(n / total) * 100}%`;
  return (
    <div>
      <div className="breadth" role="img" aria-label={`${labels.up} ${int(u)}, ${labels.flat} ${int(f)}, ${labels.down} ${int(d)}`}>
        <span className="b-up" style={{ width: w(u) }} />
        <span className="b-flat" style={{ width: w(f) }} />
        <span className="b-down" style={{ width: w(d) }} />
      </div>
      <div className="legend-row" style={{ marginTop: 6 }}>
        <span className="up">▲ {int(u)} {labels.up}</span>
        <span>● {int(f)} {labels.flat}</span>
        <span className="down">▼ {int(d)} {labels.down}</span>
      </div>
    </div>
  );
}
