import Sparkline from "./Sparkline";
import { pct, tone } from "@/lib/format";

// One headline number: label, value, the day's change as a coloured chip, an optional note and trend line.
export default function StatTile({ label, value, change, note, spark, sparkLabel, sparkCaption }: {
  label: string;
  value: string;
  change?: number | null;
  note?: React.ReactNode;
  spark?: (number | null)[];
  sparkLabel?: string;
  sparkCaption?: string;
}) {
  return (
    <div className="tile stat">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {(change != null || note) && (
        <span className="sub">
          {change != null && <span className={`chip ${tone(change)}`}>{pct(change)}</span>} {note}
        </span>
      )}
      {spark && <Sparkline values={spark} label={sparkLabel ?? label} />}
      {spark && sparkCaption && <span className="caption">{sparkCaption}</span>}
    </div>
  );
}
