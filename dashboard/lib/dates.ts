/**
 * Reading the API's two kinds of date without shifting the day.
 *
 * **Calendar dates** — a match's date, a development score's week, a
 * prediction's week — mean a day, not an instant. They arrive in two shapes:
 * bare `"2026-08-24"` from a route that serialises a `date`, and
 * `"2026-08-24T00:00:00"` from one backed by a naive `DateTime` column. `new
 * Date` reads the first as UTC midnight and the second as *local* midnight, so
 * formatting the parsed value in local time renders the bare shape a day early
 * anywhere west of Greenwich — a "next Monday" prediction dated on a Sunday.
 *
 * **Timestamps** — `created_at` — are real instants, written by the database's
 * `now()` and so in UTC, but the column carries no zone and they serialise
 * without one. `new Date` then reads them as local, putting the value hours
 * into the future: a match created at 6pm shows up dated tomorrow.
 *
 * Neither is visible in testing from one timezone, which is why both survived.
 * And "local" is not the coach's timezone anyway — the cards render in a server
 * component, so an unpinned zone is whichever one the Node process happens to
 * be in (UTC in the container, since the Dockerfile sets no TZ). Both ends of
 * every conversion here are named explicitly for that reason: the answer must
 * not depend on where the code runs.
 */

type DayWidth = "numeric" | "2-digit";

const ZONED = /(Z|[+-]\d\d:?\d\d)$/;

/**
 * The zone instants are shown in. Pinned rather than left to the renderer, per
 * the note above.
 *
 * ponytail: one zone for every academy, because there is nowhere to put a
 * per-academy one yet. Only reachable through a card whose match has no date of
 * its own, and only wrong for a coach in another province uploading near
 * midnight. A `timezone` column on `Academy` is the upgrade.
 */
const DISPLAY_ZONE = "America/Vancouver";

/**
 * The `YYYY-MM-DD` a calendar date names, whichever shape it arrived in.
 *
 * Also the right value for a `<time dateTime>`: a day carries no time for
 * another zone to move.
 */
export function isoDay(value: string): string {
  return value.slice(0, 10);
}

/** The same timestamp with its UTC zone stated rather than implied. */
export function isoInstant(value: string): string {
  return ZONED.test(value) ? value : `${value}Z`;
}

function format(date: Date, day: DayWidth, timeZone: string): string {
  // A bad value from the API would otherwise throw RangeError out of a server
  // component and take the whole page with it, rather than one card's date.
  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleDateString("en-GB", {
    day,
    month: "short",
    year: "numeric",
    timeZone,
  });
}

/** Format a calendar date as the day it names, in any reader's timezone. */
export function formatDay(value: string, day: DayWidth = "numeric"): string {
  return format(new Date(`${isoDay(value)}T00:00:00Z`), day, "UTC");
}

/** Format a UTC timestamp as the day it fell on in DISPLAY_ZONE. */
export function formatInstant(value: string): string {
  return format(new Date(isoInstant(value)), "numeric", DISPLAY_ZONE);
}
