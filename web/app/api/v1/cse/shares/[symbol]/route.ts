import { respond } from "@/lib/api";
import { shareHistory } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return respond("cse_security_metrics", await shareHistory(await getViewer(), decodeURIComponent(symbol)));
}
