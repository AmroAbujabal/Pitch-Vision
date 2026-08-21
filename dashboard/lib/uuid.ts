/**
 * UUID matching, shared by the server proxy and the login form.
 *
 * Kept in its own module with no imports rather than exported from
 * `lib/proxy.ts`, which is where it used to live: proxy.ts pulls in
 * `next/server` and `lib/session.ts`, and session.ts calls `cookies()` from
 * `next/headers`. The login page is a client component, so importing isUuid
 * from proxy.ts would drag server-only code into the browser bundle. That is
 * why the regex was duplicated instead — this is the fix that actually works.
 *
 * Same reasoning as `lib/corners.ts` and `lib/half-time.ts`: pure, dependency
 * free, unit-tested.
 *
 * Two callers with two different jobs share it deliberately. The login form
 * uses it to tell a coach their academy id is malformed before a round trip;
 * the proxy uses it to refuse a route param before interpolating it into an
 * API URL. If one of them is ever tightened — to pin a UUID version, say — the
 * other must move with it, or the form would accept an id the proxy rejects.
 */

/** Any UUID version; case-insensitive, anchored at both ends. */
export const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}
