import "server-only";

import { submitSignup } from "../db";
import type { SignupInput, SignupOutcome } from "../signup";
import { CONSENT_VERSION } from "../signup";

/** Stores one sign-up through the database's checked function; never reads any back. */
export async function sendSignup(input: SignupInput, senderKey: string): Promise<SignupOutcome> {
  try {
    return await submitSignup(input, CONSENT_VERSION, senderKey);
  } catch {
    return "unavailable"; // the database is down: say so rather than pretend it was stored
  }
}
