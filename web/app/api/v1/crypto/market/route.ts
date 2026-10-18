import { badRequest, dateParam, respond } from "@/lib/api";
import { cryptoOverview } from "@/lib/data/crypto";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// Every pair's latest day (or the latest on or before ?date=): close, returns, drawdown, volatility.
export async function GET(request: Request) {
  const date = dateParam(new URL(request.url));
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  const result = await cryptoOverview(await getViewer(), date);
  return respond("crypto_market", { access: result.access, data: result.data ? { day: result.data.day, pairs: result.data.latest } : null });
}
