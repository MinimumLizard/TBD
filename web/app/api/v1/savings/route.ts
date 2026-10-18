import { respond } from "@/lib/api";
import { savingsOverview } from "@/lib/data/savings";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET() {
  return respond("lk_savings_compare", await savingsOverview(await getViewer()));
}
