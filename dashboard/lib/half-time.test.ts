import { describe, expect, it } from "vitest";
import { parseHalfTime } from "./half-time";

describe("parseHalfTime", () => {
  it("reads mm:ss as seconds", () => {
    expect(parseHalfTime("45:30")).toEqual({ seconds: 2730, problem: null });
  });

  it("accepts hours for a long recording", () => {
    expect(parseHalfTime("1:05:00")).toEqual({ seconds: 3900, problem: null });
  });

  it("treats empty input as not stated", () => {
    expect(parseHalfTime("")).toEqual({ seconds: null, problem: null });
    expect(parseHalfTime("   ")).toEqual({ seconds: null, problem: null });
  });

  it("rejects a bare number, which is ambiguous", () => {
    // "45" could be 45 seconds or 45 minutes, and getting it wrong mirrors
    // half the match — so it is refused rather than guessed.
    expect(parseHalfTime("45").problem).not.toBeNull();
  });

  it("rejects seconds outside a minute", () => {
    expect(parseHalfTime("45:75").problem).not.toBeNull();
  });

  it("rejects nonsense", () => {
    expect(parseHalfTime("halftime").problem).not.toBeNull();
    expect(parseHalfTime("45:").problem).not.toBeNull();
    expect(parseHalfTime("-1:00").problem).not.toBeNull();
  });

  it("rejects zero, which the API rejects too", () => {
    expect(parseHalfTime("0:00").problem).not.toBeNull();
  });
});
