import { badRequest, dateParam, respond } from "@/lib/api";
import { cryptoTrend } from "@/lib/data/crypto";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// Bitcoin's two trend fits on the latest day (or the latest on or before ?date=): coefficients, bands, position.
export async function GET(request: Request) {
  const date = dateParam(new URL(request.url));
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  return respond("crypto_trend_bands", await cryptoTrend(await getViewer(), "btcusd", { date, history: false }));
}
