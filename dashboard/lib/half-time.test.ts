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

  it("accepts minutes past 59 in mm:ss, which is half-time's normal case", () => {
    expect(parseHalfTime("72:15")).toEqual({ seconds: 4335, problem: null });
  });

  it("accepts exactly 60 minutes in mm:ss", () => {
    expect(parseHalfTime("60:00")).toEqual({ seconds: 3600, problem: null });
  });

  it("agrees with the h:mm:ss spelling of the same instant", () => {
    expect(parseHalfTime("1:12:15")).toEqual({
      seconds: 4335,
      problem: null,
    });
  });

  it("rejects out-of-range minutes once hours are given", () => {
    expect(parseHalfTime("1:75:00").problem).not.toBeNull();
  });

  it("rejects a single-digit seconds component", () => {
    expect(parseHalfTime("5:5").problem).not.toBeNull();
  });

  it("accepts exactly 24 hours", () => {
    expect(parseHalfTime("1440:00")).toEqual({ seconds: 86400, problem: null });
  });

  it("rejects past 24 hours, even with a plausible-looking hours digit", () => {
    expect(parseHalfTime("1440:01").problem).not.toBeNull();
    expect(parseHalfTime("25:00:00").problem).not.toBeNull();
  });

  it("rejects an unbounded hours digit rather than overflowing downstream", () => {
    expect(parseHalfTime("999:00:00").problem).not.toBeNull();
  });
});
