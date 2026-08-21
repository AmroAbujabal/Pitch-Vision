import { describe, expect, it } from "vitest";
import { isUuid } from "./uuid";

describe("isUuid", () => {
  it("accepts the academy id the login page tells coaches to use", () => {
    expect(isUuid("18226b18-b9b6-4f1d-9cb8-1809d6b684fc")).toBe(true);
  });

  it("is case-insensitive", () => {
    expect(isUuid("18226B18-B9B6-4F1D-9CB8-1809D6B684FC")).toBe(true);
  });

  it.each([
    ["empty", ""],
    ["no dashes", "18226b18b9b64f1d9cb81809d6b684fc"],
    ["too short a final group", "18226b18-b9b6-4f1d-9cb8-1809d6b684f"],
    ["a non-hex character", "18226b18-b9b6-4f1d-9cb8-1809d6b684fg"],
    ["surrounding whitespace", " 18226b18-b9b6-4f1d-9cb8-1809d6b684fc "],
  ])("rejects %s", (_label, value) => {
    expect(isUuid(value)).toBe(false);
  });

  it("is anchored, so a valid id embedded in other text is refused", () => {
    // Unanchored, this would pass and the proxy would interpolate the whole
    // string — including the traversal — into the API URL.
    expect(isUuid("../18226b18-b9b6-4f1d-9cb8-1809d6b684fc")).toBe(false);
    expect(isUuid("18226b18-b9b6-4f1d-9cb8-1809d6b684fc/../admin")).toBe(false);
  });

  it("rejects a trailing newline", () => {
    // Pinned because the equivalent Python regex would accept this: `$` in
    // `re` matches before a final newline, so a port of this check to the API
    // side would need \Z. JavaScript's `$` (without `m`) is end-of-string, so
    // both of these are refused here.
    expect(isUuid("18226b18-b9b6-4f1d-9cb8-1809d6b684fc\n")).toBe(false);
    expect(isUuid("18226b18-b9b6-4f1d-9cb8-1809d6b684fc\nx")).toBe(false);
  });
});
