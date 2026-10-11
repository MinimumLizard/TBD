import { badRequest, dateParam, respond } from "@/lib/api";
import { shares } from "@/lib/data/cse";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const date = dateParam(new URL(request.url));
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  return respond("cse_security_metrics", await shares(await getViewer(), date));
}
