// Signing up with an e-mail address after a starting path (decision 0025; migration 0019). Accounts do not exist yet
// (docs/decisions/0016): a sign-up stores the address, with consent, so that an account can be opened for it when
// sign-ins open. Nothing is e-mailed to an address until its owner has confirmed it. The database function checks
// every field again; these checks keep a bad form from reaching it, and let the tests say exactly what is accepted.
import { answer } from "./paths";

export const MAX_EMAIL = 254;
// The wording the visitor ticked, by date: stored with each sign-up, so consent can always be traced to its text
// (messages: signup.consent). Change this date whenever that text changes.
export const CONSENT_VERSION = "2026-11-13";

export interface SignupInput {
  email: string;
  type: string | null; // the starting path the visitor came from, when there is one
  answer: string | null;
  weekly: boolean; // asked for the weekly summary
}

export type SignupOutcome = "ok" | "invalid" | "limited" | "unavailable";
export const SIGNUP_OUTCOMES: readonly SignupOutcome[] = ["ok", "invalid", "limited", "unavailable"];

// One "@", a dot in the domain, no spaces or control characters: enough to catch a slip of the keyboard. Whether the
// address exists is settled only by the confirmation e-mail.
const EMAIL = /^[^\s@<>"',;:\\]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$/;

export function cleanEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const email = value.replace(/^\s+|\s+$/g, "").toLowerCase();
  return email.length <= MAX_EMAIL && EMAIL.test(email) ? email : null;
}

/** The form's fields as a checked input; null if the address is not one, or the consent box is not ticked. */
export function parseSignup(form: { get(name: string): unknown }): SignupInput | null {
  const email = cleanEmail(form.get("email"));
  if (!email || form.get("consent") !== "yes") return null;
  const type = form.get("type");
  const key = form.get("answer");
  const known = typeof type === "string" && typeof key === "string" && answer(type, key);
  return { email, type: known ? (type as string) : null, answer: known ? (key as string) : null, weekly: form.get("weekly") === "yes" };
}

export function signupThanksPath(outcome: SignupOutcome, page: string): string {
  return `/signup/thanks?r=${outcome}&from=${encodeURIComponent(page)}`;
}
