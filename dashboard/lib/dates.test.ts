import { describe, it, expect } from "vitest";
import { formatDay, formatInstant, isoDay, isoInstant } from "./dates";

// Every assertion here holds in any process timezone: both ends of both
// conversions are pinned (calendar dates to UTC, instants to DISPLAY_ZONE), so
// nothing depends on where the test runs — which is the property the production
// bug lacked.
describe("formatDay", () => {
  it("reads a bare calendar date as the day it names", () => {
    // The prediction route sends `date.isoformat()`. Parsed as UTC midnight and
    // rendered locally, this used to read "23 Aug" — a Sunday, on a card
    // labelled "Next week".
    expect(formatDay("2026-08-24")).toBe("24 Aug 2026");
  });

  it("reads a naive datetime as the day it names", () => {
    expect(formatDay("2026-08-24T00:00:00")).toBe("24 Aug 2026");
  });

  it("gives both shapes of the same day the same answer", () => {
    expect(formatDay("2026-01-01")).toBe(formatDay("2026-01-01T00:00:00"));
  });

  it("is not moved by a time late in the UTC day", () => {
    expect(formatDay("2026-08-24T23:59:59")).toBe("24 Aug 2026");
  });

  it("pads the day when asked, for table alignment", () => {
    expect(formatDay("2026-08-03", "2-digit")).toBe("03 Aug 2026");
    expect(formatDay("2026-08-03")).toBe("3 Aug 2026");
  });
});

describe("formatInstant", () => {
  it("reads an unzoned timestamp as UTC", () => {
    // 01:00 UTC is still the previous evening in DISPLAY_ZONE. Read as the
    // renderer's local time instead, this dated a match created on the 19th to
    // the 20th — and in the container, where the renderer is UTC, it still did
    // after the first fix.
    expect(formatInstant("2026-08-20T01:00:00")).toBe("19 Aug 2026");
  });

  it("leaves an already-zoned timestamp alone", () => {
    expect(formatInstant("2026-08-20T01:00:00Z")).toBe("19 Aug 2026");
    expect(formatInstant("2026-08-19T18:00:00-07:00")).toBe("19 Aug 2026");
  });

  it("keeps a timestamp that does not cross midnight on its own day", () => {
    expect(formatInstant("2026-08-19T20:00:00")).toBe("19 Aug 2026");
  });
});

describe("a value the API should never send", () => {
  it("degrades to a dash instead of throwing", () => {
    // `lib/api.ts` casts the JSON without validating it, so `created_at: string`
    // is a compile-time promise only. Intl throws RangeError on a NaN date, and
    // these render inside a server component — one bad row would take out the
    // whole match list rather than one card's date.
    expect(formatDay("")).toBe("—");
    expect(formatDay("not-a-date")).toBe("—");
    expect(formatInstant("nonsense")).toBe("—");
  });
});

describe("machine-readable values", () => {
  it("gives a calendar date a day with no time to misread", () => {
    expect(isoDay("2026-08-24")).toBe("2026-08-24");
    expect(isoDay("2026-08-24T00:00:00")).toBe("2026-08-24");
  });

  it("marks an unzoned timestamp as the UTC it is", () => {
    // Without this, `<time dateTime>` says one day and the text beside it says
    // another.
    expect(isoInstant("2026-08-20T01:00:00")).toBe("2026-08-20T01:00:00Z");
  });

  it("leaves a zone that is already there", () => {
    expect(isoInstant("2026-08-20T01:00:00Z")).toBe("2026-08-20T01:00:00Z");
    expect(isoInstant("2026-08-19T18:00:00-07:00")).toBe(
      "2026-08-19T18:00:00-07:00",
    );
  });
});
