// An optional password over the whole site, for a private soft launch (owner, 2026-11-26): set SITE_PASSWORD on the
// host and every page and API asks for it (the browser's own sign-in box: HTTP Basic, over HTTPS); leave it unset and
// the site is open. Any user name is accepted; only the password is checked. Pure, so it can be tested.

/** True when a password is set and the request's Authorization header does not carry it. */
export function locked(authorization: string | null | undefined, password: string | undefined): boolean {
  if (!password) return false;
  const match = /^Basic\s+([A-Za-z0-9+/=]+)$/i.exec(authorization ?? "");
  if (!match) return true;
  let decoded: string;
  try {
    decoded = atob(match[1]);
  } catch {
    return true;
  }
  const given = decoded.slice(decoded.indexOf(":") + 1);
  if (decoded.indexOf(":") < 0 || given.length !== password.length) return true;
  let diff = 0; // compare every character, so the time taken says nothing about how much was right
  for (let i = 0; i < given.length; i++) diff |= given.charCodeAt(i) ^ password.charCodeAt(i);
  return diff !== 0;
}

export const LOCK_HEADERS: Record<string, string> = {
  "WWW-Authenticate": 'Basic realm="ZinvestIQ preview", charset="UTF-8"',
  "Cache-Control": "no-store",
  "X-Robots-Tag": "noindex, nofollow",
};
