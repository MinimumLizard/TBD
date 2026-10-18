import { json, respond } from "@/lib/api";
import { corporateActions } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ symbol: string }> }) {
  let symbol: string;
  try {
    symbol = decodeURIComponent((await params).symbol);
  } catch {
    return json({ error: "not_found" }, 404);
  }
  return respond("cse_corporate_actions", await corporateActions(await getViewer(), symbol));
}
