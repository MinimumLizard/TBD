import { registry } from "@/lib/registry";

// Disclaimer text comes only from compliance/disclaimers.yaml (via the generated registry): one place, one wording.
export default function Disclaimer({ keys }: { keys: string[] }) {
  return (
    <div className="disclaimer">
      {keys.map((k) => (
        <p key={k}>{registry.disclaimers[k]?.en}</p>
      ))}
    </div>
  );
}
