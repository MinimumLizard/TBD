import { badRequest, respond } from "@/lib/api";
import { companyDealings, recentDealings } from "@/lib/data/dealings";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// Directors' dealings, without names: the most recent market-wide, or one company's (?symbol=AAA or AAA.N0000).
export async function GET(request: Request) {
  const symbol = new URL(request.url).searchParams.get("symbol");
  if (symbol !== null && !/^[A-Z0-9]{1,12}(\.[A-Z0-9]{5})?$/.test(symbol)) return badRequest("symbol must be a CSE code");
  const viewer = await getViewer();
  return respond("cse_dealings", symbol ? await companyDealings(viewer, symbol) : await recentDealings(viewer));
}
