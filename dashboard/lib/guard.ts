import { redirect } from "next/navigation";
import { UnauthorizedError } from "./session";

/**
 * Turn a rejected token into a trip to the login page.
 *
 * Middleware already catches the no-cookie case, so this covers the cookie
 * that exists but has expired. Call it first in a page's catch block: pages
 * catch broadly to render an "API unreachable" card, which would otherwise
 * swallow a 401 and show the wrong message.
 */
export function redirectIfUnauthorized(error: unknown): void {
  if (error instanceof UnauthorizedError) {
    redirect("/login");
  }
}
