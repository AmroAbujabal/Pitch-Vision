/**
 * Pitch-corner geometry for the calibration picker.
 *
 * Kept pure and separate from the component because a wrong answer here is
 * invisible: canvas-space coordinates look perfectly plausible in the payload
 * and silently produce a homography that maps every player to the wrong metre.
 */

export interface Point {
  x: number;
  y: number;
}

/**
 * The order `PUT /api/v1/matches/{id}/calibration` documents. The first corner
 * maps to pitch x=0, which is what makes "low" mean the goal on the left of
 * frame.
 */
export const CORNER_LABELS = [
  "top-left",
  "top-right",
  "bottom-right",
  "bottom-left",
] as const;

/** Below this the quad is a mis-click, not a pitch. Video pixels squared. */
const MIN_AREA_PX = 10_000;

/** Cross products under this are treated as collinear. */
const COLLINEAR_EPS = 1e-6;

/**
 * One message for both order mistakes: a wrong winding and a wrong starting
 * corner have the same remedy, and the coach does not need to know which of
 * the two they made.
 */
const ORDER_PROBLEM =
  "Those corners are out of order. Clear and place them in order: top-left, top-right, bottom-right, bottom-left.";

type Rect = Pick<DOMRect, "left" | "top" | "width" | "height">;

/**
 * Convert a pointer position into the video's own pixel space.
 *
 * The canvas is drawn at the video's intrinsic resolution but rendered at
 * whatever width the layout gives it, so the ratio between the two is the only
 * thing that makes a stored corner meaningful.
 */
export function toVideoPixels(
  clientX: number,
  clientY: number,
  rect: Rect,
  videoWidth: number,
  videoHeight: number,
): Point {
  const scaleX = videoWidth / rect.width;
  const scaleY = videoHeight / rect.height;
  return {
    x: clamp(Math.round((clientX - rect.left) * scaleX), 0, videoWidth),
    y: clamp(Math.round((clientY - rect.top) * scaleY), 0, videoHeight),
  };
}

/**
 * Why these four corners cannot be used, or null if they can.
 *
 * Exactly one of the 24 orderings of four corners is right, and every other one
 * still solves — a good homography of a different pitch than the one on camera,
 * which nothing downstream can detect. Two independent things therefore need
 * testing: the direction the quad is walked (all four cross products positive
 * for clockwise in y-down pixels) and which corner comes first (winding says
 * nothing about it, so the corners are checked against the frame positions
 * their names claim, which assumes the touchline camera this project is for).
 *
 * `utils/pitch_corners.py` is the server-side twin of this function and carries
 * the full explanation of what each wrong ordering does to the analytics. Keep
 * the two in step.
 */
export function quadProblem(points: Point[]): string | null {
  if (points.length !== 4) {
    return "Place all four corners.";
  }
  // Indexed loop on purpose: a sparse array reports length 4 while some
  // entries are holes, and `some`/`every`/`filter` all skip holes rather than
  // seeing undefined, so they would wave this straight through.
  for (let i = 0; i < 4; i++) {
    if (!points[i]) return "Place all four corners.";
  }

  const crosses = points.map((_, i) =>
    cross(points[i], points[(i + 1) % 4], points[(i + 2) % 4]),
  );

  if (crosses.some((c) => Math.abs(c) < COLLINEAR_EPS)) {
    return "Those corners sit on a line. Click the four corners of the pitch itself.";
  }

  if (!crosses.every((c) => c > 0)) {
    return ORDER_PROBLEM;
  }

  const [tl, tr, br, bl] = points;
  if (!(tl.x < tr.x && bl.x < br.x && tl.y < bl.y && tr.y < br.y)) {
    return ORDER_PROBLEM;
  }

  if (shoelaceArea(points) < MIN_AREA_PX) {
    return "That area is too small to be a pitch. Click the corners of the playing surface.";
  }

  return null;
}

function cross(a: Point, b: Point, c: Point): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function shoelaceArea(points: Point[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
