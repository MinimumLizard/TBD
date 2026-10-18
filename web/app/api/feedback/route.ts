// The feedback forms post here (a plain HTML form; it works without JavaScript). The answer is always a redirect to
// the thank-you page, which says whether it was stored.
import { sendFeedback } from "@/lib/data/feedback";
import { type Outcome, isBot, parseForm, refererPath, sameOrigin, senderAddress, senderKey, thanksPath } from "@/lib/feedback";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";

function back(outcome: Outcome, page: string): Response {
  return new Response(null, { status: 303, headers: { Location: thanksPath(outcome, page), "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  const host = request.headers.get("host");
  if (!sameOrigin(request.headers.get("origin"), host)) return new Response("cross-site form posts are refused", { status: 403 });
  const fallback = refererPath(request.headers.get("referer"), host);
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return back("invalid", fallback ?? "/");
  }
  const input = parseForm(form, fallback);
  const page = input?.page ?? fallback ?? "/";
  if (isBot(form)) return back("ok", page);
  if (!input) return back("invalid", page);
  const key = senderKey(senderAddress(request.headers));
  if (!key) return back("unavailable", page);
  return back(await sendFeedback(await getViewer(), input, key), page);
}
