/**
 * Parse the coach's half-time mark.
 *
 * The value is time into the *video*, not the match clock — that is what the
 * coach is scrubbing. A bare number is refused rather than guessed at: "45"
 * reads as either 45 seconds or 45 minutes, and a wrong split mirrors half the
 * match while looking calibrated, which is the bug this input exists to remove.
 *
 * Two shapes are accepted: `mm:ss` and `h:mm:ss`. Minutes in the two-part form
 * are unbounded (`72:15`) rather than capped at 59, because half-time in a
 * full-match recording normally falls past minute 59 — any pre-match footage
 * at the head of the file pushes it there, and that is the feature's main
 * path, not an edge case. Once hours are given the minutes and seconds both
 * have to be a valid sub-60 component, same as any clock. The two patterns
 * can never both match the same input — one requires exactly one colon, the
 * other exactly two — so there is no case where they could disagree about
 * the same instant.
 *
 * `api/routers/matches.py` takes seconds and rejects anything <= 0; this
 * rejects the same values so the coach hears about it before the round trip.
 * It also caps the total at `MAX_SECONDS`, mirroring the API's `le=86_400` —
 * without it, an unbounded hours digit (`999:00:00`) would pass here and
 * overflow when `scripts/run_pipeline.py` multiplies it by fps.
 */
const HOURS_MINUTES_SECONDS = /^(\d+):([0-5]\d):([0-5]\d)$/;
const MINUTES_SECONDS = /^(\d+):([0-5]\d)$/;

const FORMAT_PROBLEM =
  "Enter the half-time mark as mm:ss — for example 45:30, or 72:15. Seconds need two digits.";

/** 24 hours — longer than any match recording. Matches the API's `le=86_400`. */
const MAX_SECONDS = 86_400;

export function parseHalfTime(value: string): {
  seconds: number | null;
  problem: string | null;
} {
  const trimmed = value.trim();
  if (!trimmed) return { seconds: null, problem: null };

  const long = HOURS_MINUTES_SECONDS.exec(trimmed);
  const short = MINUTES_SECONDS.exec(trimmed);

  let total: number;
  if (long) {
    total = Number(long[1]) * 3600 + Number(long[2]) * 60 + Number(long[3]);
  } else if (short) {
    total = Number(short[1]) * 60 + Number(short[2]);
  } else {
    return { seconds: null, problem: FORMAT_PROBLEM };
  }

  if (total <= 0) {
    return {
      seconds: null,
      problem: "Half-time cannot be at the very start of the video.",
    };
  }
  if (total > MAX_SECONDS) {
    return {
      seconds: null,
      problem: "Half-time cannot be more than 24 hours into the video.",
    };
  }
  return { seconds: total, problem: null };
}
