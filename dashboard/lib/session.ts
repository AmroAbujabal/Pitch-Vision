import { cookies } from "next/headers";

export const SESSION_COOKIE = "pv_token";

/** Thrown when the API rejects our token. Pages catch this and redirect. */
export class UnauthorizedError extends Error {
  constructor() {
    super("Not authenticated");
    this.name = "UnauthorizedError";
  }
}

export function getToken(): string | undefined {
  return cookies().get(SESSION_COOKIE)?.value;
}

/**
 * Cookie options for the session token.
 *
 * The lifetime is read from the JWT's own `exp` claim rather than duplicating
 * `settings.access_token_expire_minutes` on this side, so the cookie cannot
 * outlive the token it holds if the backend value changes. The claim is only
 * used to pick an expiry — the API still verifies the signature on every call,
 * so trusting an unverified payload for this costs nothing.
 */
export function sessionCookie(token: string) {
  return {
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: secondsUntilExpiry(token),
  };
}

const FALLBACK_MAX_AGE = 60 * 60; // an hour, if the token carries no usable exp

function secondsUntilExpiry(token: string): number {
  const payload = token.split(".")[1];
  if (!payload) return FALLBACK_MAX_AGE;
  try {
    const { exp } = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    );
    const remaining = Math.floor(exp - Date.now() / 1000);
    return remaining > 0 ? remaining : FALLBACK_MAX_AGE;
  } catch {
    return FALLBACK_MAX_AGE;
  }
}
