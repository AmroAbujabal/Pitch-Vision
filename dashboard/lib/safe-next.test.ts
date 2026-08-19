import { describe, it, expect } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it("keeps a plain pathname", () => {
    expect(safeNext("/matches")).toBe("/matches");
  });

  it("keeps the query and fragment with it", () => {
    expect(safeNext("/matches/abc?tab=players#top")).toBe(
      "/matches/abc?tab=players#top",
    );
  });

  it("falls back to the root when there is no next", () => {
    expect(safeNext(null)).toBe("/");
    expect(safeNext("")).toBe("/");
  });

  it("rejects an absolute URL", () => {
    expect(safeNext("https://evil.example/login")).toBe("/");
  });

  it("rejects a protocol-relative URL", () => {
    expect(safeNext("//evil.example")).toBe("/");
  });

  it("rejects a backslash-relative URL", () => {
    // The one a `startsWith("//")` check waves through: the URL parser reads
    // `/\` as `//` for http(s), so this used to send a signed-in coach to
    // https://evil.example/ .
    expect(safeNext("/\\evil.example")).toBe("/");
    expect(safeNext("/\\\\evil.example")).toBe("/");
    expect(safeNext("\\/evil.example")).toBe("/");
  });

  it("rejects a scheme that is not a page", () => {
    expect(safeNext("javascript:alert(1)")).toBe("/");
    expect(safeNext("data:text/html,<script>alert(1)</script>")).toBe("/");
  });

  it("normalises a path that climbs out of the site", () => {
    expect(safeNext("/../../etc/passwd")).toBe("/etc/passwd");
  });

  it("rejects a value whose normalised form is protocol-relative", () => {
    // The regression an origin check alone does not catch: each of these
    // resolves same-origin, but normalising leaves a pathname of
    // `//evil.example`, and the router resolves THAT against the real host as
    // protocol-relative. Off-site again, by the same door.
    for (const value of [
      "/..//evil.example",
      "/..//..//evil.example",
      "//dashboard.invalid//evil.example",
      "https://dashboard.invalid//evil.example",
      "//dashboard.invalid/\\evil.example",
      "//",
      "///",
    ]) {
      expect(safeNext(value)).toBe("/");
    }
  });

  it("keeps a double slash that is not protocol-relative", () => {
    // Only a leading `//` is a host. Mid-path is just a path, and rejecting it
    // would be the check over-reaching.
    expect(safeNext("/....//evil.example")).toBe("/....//evil.example");
  });

  it("rejects credentials pointing off-site", () => {
    expect(safeNext("//user:pass@evil.example")).toBe("/");
  });
});
