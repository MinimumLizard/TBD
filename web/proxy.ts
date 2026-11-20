// The front door (decision 0025). A first-time visitor sees one question at "/". Once they have answered (or chosen
// to skip), "/" opens on their own home page instead. The answer is remembered in a first-party cookie that this file
// sets when a path's page is opened: it contains "<type>.<answer>" or "skip", nothing about who the visitor is.
// Tiers are not decided here: lib/entitlements.ts stays the only tier check.
import { NextResponse, type NextRequest } from "next/server";

import { SKIPPED, START_COOKIE, isAmount, isHorizon, readStart, writeStart } from "./lib/paths";

const ONE_YEAR = 60 * 60 * 24 * 365;

function remember(response: NextResponse, value: string, request: NextRequest): NextResponse {
  response.cookies.set(START_COOKIE, value, {
    path: "/", maxAge: ONE_YEAR, sameSite: "lax", httpOnly: true, secure: request.nextUrl.protocol === "https:",
  });
  return response;
}

function go(path: string, request: NextRequest): NextResponse {
  const response = NextResponse.redirect(new URL(path, request.url));
  response.headers.set("Cache-Control", "private, no-store"); // the answer differs per visitor
  return response;
}

export function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  const saved = readStart(request.cookies.get(START_COOKIE)?.value);
  if (pathname === "/") {
    if (saved === SKIPPED) return go("/markets", request);
    if (saved) return go(`/home/${saved.type}/${saved.answer}`, request);
    return NextResponse.next();
  }
  if (pathname === "/markets") {
    // "Skip: show me the markets" on the first page: remember it, so the question is not asked at every visit
    return searchParams.get("skip") === "1" ? remember(go("/markets", request), saved ? request.cookies.get(START_COOKIE)!.value : SKIPPED, request) : NextResponse.next();
  }
  const [, type, answer] = /^\/start\/([a-z]+)\/([a-z]+)$/.exec(pathname) ?? [];
  const path = readStart(`${type}.${answer}`);
  if (!path || path === SKIPPED) return NextResponse.next();
  // the two optional questions arrive as ?amount=&horizon= (app/start/[type]/[answer]/more). Without them, a visitor
  // returning to the same path keeps what they said before.
  const amount = searchParams.get("amount"), horizon = searchParams.get("horizon");
  const asked = searchParams.has("amount") || searchParams.has("horizon");
  const kept = saved && saved !== SKIPPED && saved.type === path.type && saved.answer === path.answer ? saved : null;
  const value = writeStart(asked
    ? { ...path, amount: isAmount(amount) ? amount : null, horizon: isHorizon(horizon) ? horizon : null }
    : kept ?? path);
  return remember(NextResponse.next(), value, request);
}

export const config = { matcher: ["/", "/markets", "/start/:type/:answer"] };
