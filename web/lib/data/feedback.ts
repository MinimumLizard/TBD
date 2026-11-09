import "server-only";

import { pageVotes, submitFeedback } from "../db";
import type { FeedbackInput, Outcome } from "../feedback";
import type { Viewer } from "../entitlements";

/** Stores one piece of feedback through the database's checked function; never reads any back. */
export async function sendFeedback(viewer: Viewer, input: FeedbackInput, senderKey: string): Promise<Outcome> {
  try {
    return await submitFeedback(input, viewer.tier, senderKey);
  } catch {
    return "unavailable"; // the database is down: say so rather than pretend it was stored
  }
}

// A count is shown only once it means something: fewer readers than this and the page simply asks.
export const SHOW_COUNT_FROM = 25;

/** How many readers found a page useful, when enough have said so to be worth showing; otherwise null. */
export async function usefulCount(page: string): Promise<number | null> {
  try {
    const { useful } = await pageVotes(page);
    return useful >= SHOW_COUNT_FROM ? useful : null;
  } catch {
    return null; // the database is down: the page still asks, it just shows no count
  }
}
