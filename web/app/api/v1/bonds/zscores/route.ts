import { badRequest, dateParam, respond } from "@/lib/api";
import { bondZscores } from "@/lib/data/bonds";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const date = dateParam(new URL(request.url));
  if (date === null) return badRequest("date must be YYYY-MM-DD");
  return respond("bond_rv_zscores", await bondZscores(await getViewer(), date));
}
