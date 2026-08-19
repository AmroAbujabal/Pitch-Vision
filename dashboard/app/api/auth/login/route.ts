import { NextResponse } from "next/server";
import { BASE } from "@/lib/api";
import { sessionCookie } from "@/lib/session";

/**
 * Exchange academy credentials for a JWT and keep it server-side.
 *
 * The token is stored in an httpOnly cookie rather than returned to the page,
 * so client JavaScript never holds it. Everything that needs to call the API
 * from the browser goes through a route handler that reads the cookie here.
 */
export async function POST(request: Request) {
  const { academyId, password } = await request.json();

  if (typeof academyId !== "string" || typeof password !== "string") {
    return NextResponse.json({ error: "Missing credentials" }, { status: 400 });
  }

  // The API's /auth/token is an OAuth2 password form, and its username field
  // is the academy UUID.
  const res = await fetch(`${BASE}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: academyId, password }),
    cache: "no-store",
  });

  if (!res.ok) {
    // Deliberately does not distinguish an unknown academy from a wrong
    // password; the API goes to the trouble of constant-time verification to
    // avoid leaking which ids exist, and saying so here would undo that.
    return NextResponse.json(
      { error: "Those credentials were not accepted." },
      { status: 401 },
    );
  }

  const { access_token } = await res.json();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(sessionCookie(access_token));
  return response;
}
