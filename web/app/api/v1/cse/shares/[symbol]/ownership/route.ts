import { json, respond } from "@/lib/api";
import { companyOwnership } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// Who owns the company, at company level only (by owner type, largest block, ownership group, free float). No
// private individual is named: the tables that name people are unpublished.
export async function GET(_request: Request, { params }: { params: Promise<{ symbol: string }> }) {
  let symbol: string;
  try {
    symbol = decodeURIComponent((await params).symbol);
  } catch {
    return json({ error: "not_found" }, 404);
  }
  return respond("cse_ownership", await companyOwnership(await getViewer(), symbol.split(".")[0]));
}
