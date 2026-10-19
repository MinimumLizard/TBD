import { badRequest, dateParam, respond } from "@/lib/api";
import { flows } from "@/lib/data/dealings";
import { flowWindow } from "@/lib/dealings-display";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

// Directors' money flows per company (?window=30|90|365, ?date=YYYY-MM-DD); a free preview stops at its date.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const date = dateParam(url);
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  const window = url.searchParams.get("window");
  if (window !== null && String(flowWindow(window)) !== window) return badRequest("window must be 30, 90 or 365");
  return respond("cse_flows", await flows(await getViewer(), flowWindow(window ?? undefined), date));
}
