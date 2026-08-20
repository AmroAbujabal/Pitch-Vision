/**
 * Parse the coach's half-time mark.
 *
 * The value is time into the *video*, not the match clock — that is what the
 * coach is scrubbing. A bare number is refused rather than guessed at: "45"
 * reads as either 45 seconds or 45 minutes, and a wrong split mirrors half the
 * match while looking calibrated, which is the bug this input exists to remove.
 *
 * `api/routers/matches.py` takes seconds and rejects anything <= 0; this
 * rejects the same values so the coach hears about it before the round trip.
 */
const HMS = /^(?:(\d+):)?([0-5]?\d):([0-5]\d)$/;

export function parseHalfTime(value: string): {
  seconds: number | null;
  problem: string | null;
} {
  const trimmed = value.trim();
  if (!trimmed) return { seconds: null, problem: null };

  const match = HMS.exec(trimmed);
  if (!match) {
    return {
      seconds: null,
      problem: "Enter the half-time mark as mm:ss (for example 45:30).",
    };
  }

  const [, hours, minutes, seconds] = match;
  const total =
    Number(hours ?? 0) * 3600 + Number(minutes) * 60 + Number(seconds);

  if (total <= 0) {
    return {
      seconds: null,
      problem: "Half-time cannot be at the very start of the video.",
    };
  }
  return { seconds: total, problem: null };
}
