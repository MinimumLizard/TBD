import { respond } from "@/lib/api";
import { lab } from "@/lib/data/lab";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// The portfolio lab's example portfolio, its record and its reviews (Pro, decision 0027).
export async function GET() {
  return respond("cse_lab_backtest", await lab(await getViewer()));
}
