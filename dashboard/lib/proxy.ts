import { NextResponse } from "next/server";
import { BASE } from "./api";
import { getToken } from "./session";

/**
 * Forward a browser request to the API with the session token attached.
 *
 * Client components cannot call the API directly: the token lives in an
 * httpOnly cookie precisely so that page JavaScript cannot read it. These
 * handlers are the only place the two sides meet.
 */
export async function forward(
  path: string,
  init: RequestInit,
): Promise<NextResponse> {
  const token = getToken();
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const body = await res.text();
  if (!res.ok) {
    return NextResponse.json(
      { error: errorMessage(body, res.status) },
      { status: res.status },
    );
  }
  return new NextResponse(body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("content-type") ?? "application/json",
    },
  });
}

/**
 * Route params land in the API URL, so they are checked before interpolation
 * rather than trusted because Next produced them.
 *
 * Re-exported rather than moved so the route handlers importing it from here
 * keep working; the definition lives in `lib/uuid.ts` because the login page
 * needs it too and cannot import this module.
 */
export { isUuid } from "./uuid";

export const badId = () =>
  NextResponse.json({ error: "Invalid match id" }, { status: 400 });

/** Pull FastAPI's `detail` out of an error body, falling back to the status. */
function errorMessage(body: string, status: number): string {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // not JSON; fall through
  }
  return `Request failed (${status})`;
}
