// The sign-up form posts here (a plain HTML form; it works without JavaScript). The answer is always a redirect to
// the thank-you page, which says whether the address was stored, and never whether it was already there.
import { sendSignup } from "@/lib/data/signup";
import { isBot, refererPath, sameOrigin, senderAddress, senderKey, sitePath } from "@/lib/feedback";
import { type SignupOutcome, parseSignup, signupThanksPath } from "@/lib/signup";

export const dynamic = "force-dynamic";

function back(outcome: SignupOutcome, page: string): Response {
  return new Response(null, { status: 303, headers: { Location: signupThanksPath(outcome, page), "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  const host = request.headers.get("host");
  if (!sameOrigin(request.headers.get("origin"), host)) return new Response("cross-site form posts are refused", { status: 403 });
  const fallback = refererPath(request.headers.get("referer"), host) ?? "/";
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return back("invalid", fallback);
  }
  const page = sitePath(form.get("page")) ?? fallback;
  if (isBot(form)) return back("ok", page);
  const input = parseSignup(form);
  if (!input) return back("invalid", page);
  const key = senderKey(senderAddress(request.headers));
  if (!key) return back("unavailable", page);
  return back(await sendSignup(input, key), page);
}
