// A small ring chart drawn as plain SVG on the server: no script, so it reads the same on a slow phone and in the
// static preview. Colours are the theme's series tokens (app/globals.css), the last slice ("other") in the muted ink.
const COLOURS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];

export interface Slice {
  label: string;
  value: number; // a share of the whole, 0..1
}

export default function Donut({ slices, centre, centreSub, label, other }: {
  slices: Slice[];
  centre: string;
  centreSub: string;
  label: string;
  other?: string; // the label of a last slice holding the rest, drawn in the muted colour
}) {
  const r = 40;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const arcs = slices.map((s, i) => {
    const length = Math.max(0, s.value) * c;
    const colour = other && i === slices.length - 1 && s.label === other ? "var(--border-strong)" : COLOURS[i % COLOURS.length];
    const arc = { colour, dash: `${length} ${c - length}`, offset: -offset, slice: s };
    offset += length;
    return arc;
  });
  return (
    <figure className="donut">
      <svg viewBox="0 0 100 100" role="img" aria-label={label}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="16" />
        {arcs.map((a) => (
          <circle key={a.slice.label} cx="50" cy="50" r={r} fill="none" stroke={a.colour} strokeWidth="16"
                  strokeDasharray={a.dash} strokeDashoffset={a.offset} transform="rotate(-90 50 50)" />
        ))}
        <text x="50" y="50" textAnchor="middle" className="donut-centre">{centre}</text>
        <text x="50" y="62" textAnchor="middle" className="donut-sub">{centreSub}</text>
      </svg>
      <ul className="donut-legend">
        {arcs.map((a) => (
          <li key={a.slice.label}>
            <span className="swatch" style={{ background: a.colour }} aria-hidden="true" />
            <span className="dl-label">{a.slice.label}</span>
            <span className="dl-value">{Math.round(a.slice.value * 100)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
