// Visitors' feedback (docs/plan-retail-features.md §3 A; migration 0012). The database function checks every field
// again; these checks are here so a bad form never reaches it, and so the tests can say exactly what is accepted.
// Nothing a visitor writes is ever shown on the site.
import { createHmac } from "node:crypto";

export const TOPICS = ["data_error", "unclear", "idea", "other"] as const;
export type Topic = (typeof TOPICS)[number];
export const MAX_MESSAGE = 2000;
export const MIN_MESSAGE = 3;

export type FeedbackInput =
  | { kind: "page_vote"; page: string; useful: boolean }
  | { kind: "message"; page: string; topic: Topic; message: string };

export type Outcome = "ok" | "invalid" | "limited" | "unavailable";
export const OUTCOMES: readonly Outcome[] = ["ok", "invalid", "limited", "unavailable"];

const PATH = /^\/[A-Za-z0-9/_.:%~-]{0,200}$/;

/** A path on this site (no scheme, host, query or fragment), or null. */
export function sitePath(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return PATH.test(value) && !value.startsWith("//") ? value : null;
}

/** The path of a Referer header, only if it points at this same site. */
export function refererPath(referer: string | null, host: string | null): string | null {
  if (!referer || !host) return null;
  try {
    const url = new URL(referer);
    return url.host === host ? sitePath(url.pathname) : null;
  } catch {
    return null;
  }
}

/** A form post from another site is refused (browsers send Origin on every cross-site form post). */
export function sameOrigin(origin: string | null, host: string | null): boolean {
  if (!origin) return true;
  if (!host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** The form's fields as a checked input, or null if anything is missing or out of bounds. */
export function parseForm(form: { get(name: string): unknown }, fallbackPage: string | null): FeedbackInput | null {
  const page = sitePath(form.get("page")) ?? fallbackPage ?? "/";
  const kind = form.get("kind");
  if (kind === "page_vote") {
    const useful = form.get("useful");
    if (useful !== "yes" && useful !== "no") return null;
    return { kind, page, useful: useful === "yes" };
  }
  if (kind === "message") {
    const topic = form.get("topic");
    const raw = form.get("message");
    if (typeof topic !== "string" || !(TOPICS as readonly string[]).includes(topic) || typeof raw !== "string") return null;
    const message = raw.replace(/^\s+|\s+$/g, "");
    if (message.length < MIN_MESSAGE || message.length > MAX_MESSAGE) return null;
    return { kind, page, topic: topic as Topic, message };
  }
  return null;
}

/** A bot filling every field fills the hidden one too; its post is thanked and dropped. */
export function isBot(form: { get(name: string): unknown }): boolean {
  const trap = form.get("website");
  return typeof trap === "string" && trap.length > 0;
}

// The sender's network address is never stored: only this keyed hash, which the database uses to limit how often
// one sender can write, and forgets after seven days. A deployed site must set FEEDBACK_KEY_SECRET (any long random
// text); without it there, feedback is switched off rather than hashed with a key anyone can read in this repo.
export function senderKey(address: string, env: NodeJS.ProcessEnv = process.env): string | null {
  const deployed = env.APP_ENV === "production" || !!env.VERCEL || !!env.VERCEL_ENV;
  const secret = env.FEEDBACK_KEY_SECRET || (deployed ? null : "local-development-only");
  if (!secret) return null;
  return createHmac("sha256", secret).update(address).digest("hex").slice(0, 32);
}

/** The visitor's address as the hosting platform reports it (the first X-Forwarded-For entry on Vercel). */
export function senderAddress(headers: { get(name: string): string | null }): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].replace(/^\s+|\s+$/g, "");
  return headers.get("x-real-ip") ?? "unknown";
}

export function thanksPath(outcome: Outcome, page: string): string {
  return `/feedback/thanks?r=${outcome}&from=${encodeURIComponent(page)}`;
}
