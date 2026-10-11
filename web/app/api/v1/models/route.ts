import { json } from "@/lib/api";
import { authorize } from "@/lib/entitlements";
import { MODEL_NAMES, modelEntry } from "@/lib/registry";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// The catalogue: every model, its minimum tier, and what this visitor may see. No model outputs.
export async function GET() {
  const viewer = await getViewer();
  return json({
    viewer_tier: viewer.tier,
    models: MODEL_NAMES.map((name) => {
      const entry = modelEntry(name);
      const access = authorize(viewer, name);
      return {
        model: name,
        market: entry.market,
        method_version: entry.current_version,
        minimum_tier: entry.minimum_tier,
        access: access.allowed ? (access.maxDate ? "preview" : "full") : "none",
        method_url: `/methods/${name}`,
      };
    }),
  });
}
