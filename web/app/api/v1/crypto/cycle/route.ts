import { badRequest, dateParam, json, respond } from "@/lib/api";
import { assetByPair } from "@/lib/crypto-display";
import { cryptoCycle } from "@/lib/data/crypto";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// One pair's cycle measures on its latest day (or the latest on or before ?date=): ?pair=btcusd (the default).
export async function GET(request: Request) {
  const url = new URL(request.url);
  const date = dateParam(url);
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  const pair = url.searchParams.get("pair") ?? "btcusd";
  if (!assetByPair(pair)?.cycle) return json({ error: "not_found" }, 404);
  const result = await cryptoCycle(await getViewer(), pair, { date, history: false });
  return respond("crypto_cycle", {
    access: result.access,
    data: result.data ? { day: result.data.day, latest: result.data.daily[0] ?? null, crossings: result.data.events, cycle_table: result.data.anchors, months: result.data.months } : null,
  });
}
