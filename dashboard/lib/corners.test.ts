import { describe, it, expect } from "vitest";
import {
  CORNER_LABELS,
  toVideoPixels,
  quadProblem,
  type Point,
} from "./corners";

// A canvas rendered at 640x360 showing a 1920x1080 video: every click scales 3x.
const RECT = { left: 0, top: 0, width: 640, height: 360 };
const VIDEO = { width: 1920, height: 1080 };

describe("toVideoPixels", () => {
  it("scales a click from canvas space to video space", () => {
    expect(toVideoPixels(640, 360, RECT, VIDEO.width, VIDEO.height)).toEqual({
      x: 1920,
      y: 1080,
    });
  });

  it("subtracts the element offset before scaling", () => {
    const offset = { left: 100, top: 50, width: 640, height: 360 };
    expect(toVideoPixels(420, 230, offset, VIDEO.width, VIDEO.height)).toEqual({
      x: 960,
      y: 540,
    });
  });

  it("is independent of how large the canvas renders", () => {
    // The same relative point on three different canvas sizes must land on the
    // same video pixel. This is the failure that is invisible in the UI: a
    // canvas-space coordinate looks plausible and silently ruins the homography.
    const sizes = [320, 640, 1280];
    const results = sizes.map((w) =>
      toVideoPixels(
        w * 0.25,
        w * 0.25 * (9 / 16),
        { left: 0, top: 0, width: w, height: w * (9 / 16) },
        VIDEO.width,
        VIDEO.height,
      ),
    );
    for (const r of results) {
      expect(r).toEqual({ x: 480, y: 270 });
    }
  });

  it("clamps a click outside the frame to the frame", () => {
    expect(toVideoPixels(-40, 999, RECT, VIDEO.width, VIDEO.height)).toEqual({
      x: 0,
      y: 1080,
    });
  });

  it("rounds to whole pixels", () => {
    const p = toVideoPixels(101, 67, RECT, VIDEO.width, VIDEO.height);
    expect(Number.isInteger(p.x)).toBe(true);
    expect(Number.isInteger(p.y)).toBe(true);
  });
});

describe("quadProblem", () => {
  // TL -> TR -> BR -> BL, the order the API documents.
  const perspective: Point[] = [
    { x: 400, y: 300 }, // near touchline is wider in a real camera view
    { x: 1500, y: 300 },
    { x: 1850, y: 1000 },
    { x: 70, y: 1000 },
  ];

  it("accepts a realistic perspective quad", () => {
    expect(quadProblem(perspective)).toBeNull();
  });

  it("accepts a plain rectangle", () => {
    expect(
      quadProblem([
        { x: 0, y: 0 },
        { x: 1920, y: 0 },
        { x: 1920, y: 1080 },
        { x: 0, y: 1080 },
      ]),
    ).toBeNull();
  });

  it("rejects fewer than four corners", () => {
    expect(quadProblem(perspective.slice(0, 3))).toMatch(/four/i);
  });

  it("rejects four collinear points", () => {
    // A singular homography the pipeline cannot fit, and nothing downstream
    // would report it as an error.
    expect(
      quadProblem([
        { x: 100, y: 100 },
        { x: 400, y: 400 },
        { x: 700, y: 700 },
        { x: 1000, y: 1000 },
      ]),
    ).toMatch(/line/i);
  });

  it("rejects three collinear points", () => {
    expect(
      quadProblem([
        { x: 100, y: 100 },
        { x: 500, y: 100 },
        { x: 900, y: 100 },
        { x: 500, y: 800 },
      ]),
    ).toMatch(/line/i);
  });

  it("rejects a self-intersecting bowtie", () => {
    // Corners clicked in the wrong order: TR and BR swapped.
    expect(
      quadProblem([
        { x: 400, y: 300 },
        { x: 1500, y: 300 },
        { x: 70, y: 1000 },
        { x: 1850, y: 1000 },
      ]),
    ).toMatch(/order|cross/i);
  });

  it("rejects duplicate points", () => {
    expect(
      quadProblem([
        { x: 400, y: 300 },
        { x: 400, y: 300 },
        { x: 1850, y: 1000 },
        { x: 70, y: 1000 },
      ]),
    ).toBeTruthy();
  });

  it("rejects a quad too small to be a pitch", () => {
    expect(
      quadProblem([
        { x: 100, y: 100 },
        { x: 104, y: 100 },
        { x: 104, y: 104 },
        { x: 100, y: 104 },
      ]),
    ).toMatch(/small/i);
  });
});

describe("CORNER_LABELS", () => {
  it("is the TL -> TR -> BR -> BL order the API documents", () => {
    expect(CORNER_LABELS).toEqual([
      "top-left",
      "top-right",
      "bottom-right",
      "bottom-left",
    ]);
  });
});

describe("quadProblem with an incomplete corner list", () => {
  // Regression: typing into the manual coordinate boxes before clicking any
  // corner used to build a sparse array, and a hole reads as a Point to both
  // quadProblem and the canvas draw loop.
  it("rejects a four-length array containing holes rather than throwing", () => {
    const sparse: Point[] = [];
    sparse[3] = { x: 100, y: 100 };
    expect(() => quadProblem(sparse)).not.toThrow();
    expect(quadProblem(sparse)).toBeTruthy();
  });

  it("rejects a list padded with origin placeholders", () => {
    // What the fixed setCorner produces: dense, but three corners still at 0,0.
    expect(
      quadProblem([
        { x: 0, y: 0 },
        { x: 0, y: 0 },
        { x: 0, y: 0 },
        { x: 1620, y: 880 },
      ]),
    ).toBeTruthy();
  });
});
