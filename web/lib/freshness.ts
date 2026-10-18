// Is the data as recent as the market calendar says it should be? Computed on the server, from the trading
// calendars in config/calendars (copied into the generated registry), so a page can say when it is behind.
import { registry } from "./registry";
import { addDays } from "./time";

// Hour (Sri Lanka time) after which a session's data is normally published and collected.
// Crypto: a UTC day ends at 05:30 Sri Lanka time and is collected at 05:47; by 06:30 yesterday's close is expected.
const PUBLISHED_BY_HOUR: Record<string, number> = { cse: 17, lk_bond_market: 20, crypto: 6.5 };

export function isSession(calendar: string, iso: string): boolean {
  const cal = registry.calendars[calendar];
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return (cal.every_day || (day !== 0 && day !== 6)) && !cal.closures.includes(iso);
}

/** The latest session whose data should have been published by `now`. */
export function expectedSession(calendar: string, now: Date = new Date()): string {
  const slt = new Date(now.getTime() + 5.5 * 3600 * 1000);
  let day = slt.toISOString().slice(0, 10);
  if (slt.getUTCHours() + slt.getUTCMinutes() / 60 < PUBLISHED_BY_HOUR[calendar]) day = addDays(day, -1);
  // a market that never closes publishes a UTC day after it ends: the expected day is the one before
  if (registry.calendars[calendar].every_day) day = addDays(day, -1);
  while (!isSession(calendar, day)) day = addDays(day, -1);
  return day;
}

/** Sessions that should exist after `dataDate`, up to and including the expected one. */
export function sessionsBehind(calendar: string, dataDate: string, now: Date = new Date()): number {
  const expected = expectedSession(calendar, now);
  let n = 0;
  for (let d = addDays(dataDate, 1); d <= expected; d = addDays(d, 1)) if (isSession(calendar, d)) n += 1;
  return n;
}
