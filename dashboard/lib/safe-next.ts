/**
 * Keep post-login navigation on this site.
 *
 * `middleware.ts` only ever sets `next` to a pathname, but the query string is
 * whatever the visitor's URL says, so a crafted link would otherwise hand a
 * freshly signed-in coach to someone else's page.
 *
 * Prefix checks are not enough here. Rejecting `//host` looks like it covers
 * protocol-relative URLs, but the WHATWG parser treats a backslash as a slash
 * for http(s), so `/\evil.example` resolves to `https://evil.example/` exactly
 * like `//evil.example` does. Resolving the value and comparing origins asks
 * the same question the browser will, instead of guessing which spellings of
 * "off-site" exist.
 *
 * That has to be asked twice. Normalising a same-origin URL can produce a
 * pathname that is itself off-origin: `/..//evil.example` resolves to
 * `https://dashboard.invalid//evil.example`, whose pathname is
 * `//evil.example`, and `router.replace` resolves that against the real host as
 * protocol-relative — straight back off-site. So only a value that survives its
 * own output is returned.
 */

/**
 * Any fixed origin works: it stands in for wherever the dashboard is served
 * from, and a value that escapes it would escape the real one too. A literal
 * keeps this usable during server rendering, where `location` does not exist.
 */
const HERE = "https://dashboard.invalid";

/** The same-origin path `value` names, or null if it points anywhere else. */
function samePath(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value, HERE);
  } catch {
    return null;
  }
  if (url.origin !== HERE) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}

export function safeNext(value: string | null): string {
  if (!value) return "/";
  const path = samePath(value);
  // A path that does not resolve to itself is one the router would read
  // differently than this check did.
  if (path === null || samePath(path) !== path) return "/";
  return path;
}
