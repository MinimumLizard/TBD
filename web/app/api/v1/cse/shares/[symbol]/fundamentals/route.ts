import { json, respond } from "@/lib/api";
import { companyFigures } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// The company's figures (EPS, net assets per share, P/E, P/B, ROE, dividend yield) at the latest session.
export async function GET(_request: Request, { params }: { params: Promise<{ symbol: string }> }) {
  let symbol: string;
  try {
    symbol = decodeURIComponent((await params).symbol);
  } catch {
    return json({ error: "not_found" }, 404);
  }
  return respond("cse_fundamentals", await companyFigures(await getViewer(), symbol.split(".")[0]));
}
