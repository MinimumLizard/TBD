import { json, respond } from "@/lib/api";
import { shareHistory } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ symbol: string }> }) {
  const raw = (await params).symbol;
  let symbol: string;
  try {
    symbol = decodeURIComponent(raw);
  } catch {
    return json({ error: "not_found" }, 404);
  }
  const result = await shareHistory(await getViewer(), symbol);
  if (result.access.allowed && result.data?.length === 0) return json({ error: "not_found" }, 404);
  return respond("cse_security_metrics", result);
}
