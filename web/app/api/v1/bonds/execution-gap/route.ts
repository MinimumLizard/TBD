import { respond } from "@/lib/api";
import { executionGap } from "@/lib/data/bonds";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET() {
  return respond("bond_execution_gap", await executionGap(await getViewer()));
}
