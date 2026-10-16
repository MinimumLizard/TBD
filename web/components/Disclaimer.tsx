import { registry } from "@/lib/registry";

// Shown once on every page, in the site footer; a page never repeats them.
export const SITE_WIDE_DISCLAIMERS = ["general", "data_sources"];

// Disclaimer text comes only from compliance/disclaimers.yaml (via the generated registry): one place, one wording.
export default function Disclaimer({ keys }: { keys: string[] }) {
  if (keys.length === 0) return null;
  return (
    <div className="disclaimer">
      {keys.map((k) => (
        <p key={k}>{registry.disclaimers[k]?.en}</p>
      ))}
    </div>
  );
}
