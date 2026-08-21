"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Loader2,
  RotateCcw,
  Trash2,
  Upload as UploadIcon,
  Video,
} from "lucide-react";
import StepIndicator from "./StepIndicator";
import SmallButton from "./SmallButton";
import {
  CORNER_LABELS,
  quadProblem,
  toVideoPixels,
  type Point,
} from "@/lib/corners";
import { parseHalfTime } from "@/lib/half-time";

/** Dots render small but must stay tappable. */
const DOT_RADIUS = 5;
const HIT_RADIUS = 22;

const STEPS = ["Choose video", "Mark corners", "Direction", "Save", "Upload"];

type DefendsEnd = "low" | "high";

export default function CalibratePicker({ matchId }: { matchId: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [frame, setFrame] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [corners, setCorners] = useState<Point[]>([]);
  const [defendsEnd, setDefendsEnd] = useState<DefendsEnd | null>(null);
  const [halfTime, setHalfTime] = useState("");
  const [saved, setSaved] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [busy, setBusy] = useState<"saving" | "uploading" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Revoke the object URL when the component unmounts or the file changes,
  // otherwise the decoded video stays in memory for the life of the tab.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video || !frame) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Sized here rather than in the `seeked` handler: the canvas is only
    // mounted once `frame` is set, so it does not exist yet at seek time.
    if (canvas.width !== frame.width) canvas.width = frame.width;
    if (canvas.height !== frame.height) canvas.height = frame.height;

    ctx.drawImage(video, 0, 0, frame.width, frame.height);

    if (corners.length > 1) {
      ctx.beginPath();
      ctx.moveTo(corners[0].x, corners[0].y);
      corners.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
      if (corners.length === 4) ctx.closePath();
      ctx.strokeStyle = "#1E40AF";
      ctx.lineWidth = Math.max(2, frame.width / 400);
      ctx.stroke();
    }

    const dot = Math.max(DOT_RADIUS, frame.width / 180);
    corners.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, dot, 0, Math.PI * 2);
      ctx.fillStyle = "#1E40AF";
      ctx.fill();
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = Math.max(1.5, frame.width / 700);
      ctx.stroke();

      // Numbered, not just coloured: corner 2 and corner 3 are otherwise
      // indistinguishable to anyone who cannot separate them by position.
      ctx.fillStyle = "#FFFFFF";
      ctx.font = `600 ${dot * 1.8}px "Fira Code", monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(i + 1), p.x, p.y + dot * 2.6);
      ctx.fillStyle = "#1E40AF";
      ctx.fillText(String(i + 1), p.x, p.y + dot * 2.5);
    });
  }, [corners, frame]);

  useEffect(() => {
    draw();
  }, [draw]);

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0];
    if (!picked) return;

    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    setError(null);
    setCorners([]);
    setDefendsEnd(null);
    setSaved(false);
    setUploaded(false);
    setFrame(null);
    setFile(picked);

    const url = URL.createObjectURL(picked);
    objectUrlRef.current = url;

    const video = document.createElement("video");
    video.preload = "auto";
    video.muted = true;
    video.src = url;
    videoRef.current = video;

    // A video swapped while the previous one is still decoding leaves the old
    // element's listeners attached, and revoking its URL fires its `error`
    // handler — which would clear the file the coach just picked and name the
    // wrong one. Every handler checks it is still the current video first.
    const isCurrent = () => videoRef.current === video;

    video.addEventListener("error", () => {
      if (!isCurrent()) return;
      setError(
        `This browser could not decode ${picked.name}. The API also accepts .avi and .mkv, which often will not play here; use the .mp4 or .mov of the same match to pick corners.`,
      );
      setFile(null);
    });

    video.addEventListener("loadeddata", () => {
      if (!isCurrent()) return;
      // A couple of seconds in, so the first frame of a fade-in is not what
      // the coach has to click on.
      video.currentTime = Math.min(2, (video.duration || 4) / 2);
    });

    video.addEventListener("seeked", () => {
      if (!isCurrent()) return;
      setFrame({ width: video.videoWidth, height: video.videoHeight });
    });
  }

  function onCanvasClick(event: React.MouseEvent<HTMLCanvasElement>) {
    if (!frame) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const point = toVideoPixels(
      event.clientX,
      event.clientY,
      rect,
      frame.width,
      frame.height,
    );
    const scale = frame.width / rect.width;

    // Functional update: two clicks landing in the same React batch would
    // otherwise both read the same corner list and only the last would stick.
    setCorners((prev) => {
      if (prev.length >= 4) return prev;
      const tooClose = prev.some(
        (c) => Math.hypot(c.x - point.x, c.y - point.y) < HIT_RADIUS * scale,
      );
      return tooClose ? prev : [...prev, point];
    });
    setSaved(false);
  }

  function setCorner(index: number, axis: "x" | "y", raw: string) {
    const value = Number(raw);
    if (!Number.isFinite(value) || !frame) return;

    // Clamped to the frame for the same reason toVideoPixels clamps a click:
    // a corner outside the video fits a homography perfectly happily and then
    // maps players to metres that are simply wrong, with nothing to show for
    // it. The `max` attribute alone does not stop a typed value.
    const limit = axis === "x" ? frame.width : frame.height;
    const clamped = Math.min(Math.max(Math.round(value), 0), limit);

    setCorners((prev) => {
      // Filling the gap keeps the array dense. Assigning straight to `index`
      // would leave holes when an earlier corner has not been placed, and a
      // hole is read as a Point by both draw() and quadProblem().
      const next = [...prev];
      while (next.length < index) next.push({ x: 0, y: 0 });
      next[index] = { ...(next[index] ?? { x: 0, y: 0 }), [axis]: clamped };
      return next;
    });
    setSaved(false);
  }

  const problem = corners.length === 4 ? quadProblem(corners) : null;
  const halfTimeParsed = parseHalfTime(halfTime);
  const canSave =
    corners.length === 4 &&
    !problem &&
    defendsEnd !== null &&
    halfTimeParsed.problem === null;

  async function save() {
    if (!canSave) return;
    setBusy("saving");
    setError(null);
    try {
      const res = await fetch(`/api/matches/${matchId}/calibration`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pitch_corners: corners.map((p) => [p.x, p.y]),
          home_defends_end: defendsEnd,
          half_time_seconds: halfTimeParsed.seconds,
        }),
      });
      if (!res.ok) {
        const body = await res.json();
        setError(body.error ?? "Could not save the calibration.");
        return;
      }
      setSaved(true);
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(null);
    }
  }

  async function upload() {
    if (!file || !saved) return;
    setBusy("uploading");
    setError(null);
    try {
      const form = new FormData();
      // `frame` is the decoded size of this exact file — it is only ever set
      // behind the isCurrent() guard above, and a file that fails to decode
      // clears itself — so it cannot describe a different one.
      // POST /matches/ had to guess these; the guess is what gets corrected.
      if (frame) {
        form.append("frame_width", String(frame.width));
        form.append("frame_height", String(frame.height));
      }
      form.append("file", file);
      const res = await fetch(`/api/matches/${matchId}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json();
        setError(body.error ?? "Could not upload the video.");
        return;
      }
      setUploaded(true);
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(null);
    }
  }

  const nextCorner = CORNER_LABELS[corners.length];

  return (
    <div className="space-y-5">
      <StepIndicator
        labels={STEPS}
        current={
          uploaded ? 4 : saved ? 3 : corners.length === 4 ? 2 : frame ? 1 : 0
        }
      />

      {error && (
        <p
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="section-title">Pitch corners</h2>
          {frame && (
            <span className="text-2xs text-slate-400">
              <span className="tabular-nums">
                {frame.width} x {frame.height}
              </span>{" "}
              source pixels
            </span>
          )}
        </div>

        {!frame ? (
          <label
            htmlFor="video-file"
            className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-slate-200 px-6 py-16 text-center transition-colors hover:border-primary-200 hover:bg-primary-50/40 focus-within:ring-2 focus-within:ring-primary-500"
          >
            <Video className="h-6 w-6 text-slate-300" aria-hidden="true" />
            <span className="text-sm font-medium text-slate-700">
              Choose the match video
            </span>
            <span className="max-w-sm text-xs leading-relaxed text-slate-400">
              A still is taken in your browser so you can mark the pitch. The
              file is not uploaded until calibration is saved.
            </span>
            <input
              id="video-file"
              type="file"
              accept="video/*"
              className="sr-only"
              onChange={onFileChange}
            />
          </label>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-700">
                {corners.length < 4 ? (
                  <>
                    Click the{" "}
                    <strong className="font-semibold text-primary-800">
                      {nextCorner}
                    </strong>{" "}
                    corner of the pitch.
                  </>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-emerald-700">
                    <Check className="h-4 w-4" aria-hidden="true" />
                    All four corners placed.
                  </span>
                )}
              </p>
              <div className="flex gap-2">
                <SmallButton
                  onClick={() => {
                    setCorners(corners.slice(0, -1));
                    setSaved(false);
                  }}
                  disabled={corners.length === 0}
                  icon={RotateCcw}
                  label="Undo"
                />
                <SmallButton
                  onClick={() => {
                    setCorners([]);
                    setSaved(false);
                  }}
                  disabled={corners.length === 0}
                  icon={Trash2}
                  label="Clear"
                />
              </div>
            </div>

            <canvas
              ref={canvasRef}
              onClick={onCanvasClick}
              aria-label={`Match still. ${corners.length} of 4 pitch corners placed.`}
              className="w-full cursor-crosshair rounded-lg border border-slate-200"
            />

            {problem && (
              <p
                role="alert"
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
              >
                {problem}
              </p>
            )}

            <details className="rounded-md border border-slate-200 px-3 py-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600">
                Enter coordinates instead
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {CORNER_LABELS.map((label, i) => (
                  <fieldset key={label} className="flex flex-col gap-1.5">
                    <legend className="text-2xs font-semibold uppercase tracking-wider text-slate-400">
                      {i + 1}. {label}
                    </legend>
                    <div className="flex gap-2">
                      {(["x", "y"] as const).map((axis) => (
                        <span
                          key={axis}
                          className="flex flex-1 items-center gap-1"
                        >
                          <label
                            htmlFor={`corner-${i}-${axis}`}
                            className="text-2xs text-slate-400"
                          >
                            {axis}
                          </label>
                          <input
                            id={`corner-${i}-${axis}`}
                            type="number"
                            min={0}
                            max={axis === "x" ? frame.width : frame.height}
                            value={corners[i]?.[axis] ?? ""}
                            onChange={(e) => setCorner(i, axis, e.target.value)}
                            className="w-full rounded border border-slate-200 px-2 py-1 font-mono text-xs text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                          />
                        </span>
                      ))}
                    </div>
                  </fieldset>
                ))}
              </div>
            </details>
          </div>
        )}
      </div>

      {corners.length === 4 && !problem && (
        <div className="card">
          <h2 className="section-title mb-1">Attacking direction</h2>
          <p className="mb-4 text-sm text-slate-500">
            This cannot be worked out from the corners, and getting it backwards
            reports every formation mirrored. A 4-2-3-1 comes back as 1-3-2-4.
          </p>
          <div className="flex flex-col gap-2">
            {(
              [
                ["low", "Home defends the left goal"],
                ["high", "Home defends the right goal"],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                className="flex cursor-pointer items-center gap-3 rounded-md border border-slate-200 px-3 py-2.5 text-sm text-slate-700 transition-colors hover:border-primary-200 hover:bg-primary-50/40 focus-within:ring-2 focus-within:ring-primary-500"
              >
                <input
                  type="radio"
                  name="defends-end"
                  value={value}
                  checked={defendsEnd === value}
                  onChange={() => {
                    setDefendsEnd(value);
                    setSaved(false);
                  }}
                  className="h-4 w-4 accent-primary-800"
                />
                {label}
              </label>
            ))}
          </div>

          <p className="mt-2 text-xs text-slate-400">
            Left and right as they appear in the still above.
          </p>

          <div className="mt-4 border-t border-slate-100 pt-4">
            <label
              htmlFor="half-time"
              className="text-sm font-medium text-slate-700"
            >
              Half-time (optional)
            </label>
            <p id="half-time-help" className="mt-1 text-xs text-slate-400">
              If this video covers both halves, the time on the video when the
              teams changed ends — mm:ss. Leave it blank for a single half.
            </p>
            <input
              id="half-time"
              type="text"
              placeholder="45:30"
              value={halfTime}
              onChange={(e) => {
                setHalfTime(e.target.value);
                setSaved(false);
              }}
              aria-describedby={
                halfTimeParsed.problem
                  ? "half-time-help half-time-error"
                  : "half-time-help"
              }
              aria-invalid={halfTimeParsed.problem !== null}
              className="mt-2 w-32 rounded border border-slate-200 px-2 py-1 font-mono text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            />
            {halfTimeParsed.problem && (
              <p
                id="half-time-error"
                role="alert"
                className="mt-2 text-xs text-amber-700"
              >
                {halfTimeParsed.problem}
              </p>
            )}
          </div>
        </div>
      )}

      <div className="card flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={!canSave || busy !== null || saved}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-primary-800 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "saving" && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          {saved ? "Calibration saved" : "Save calibration"}
        </button>

        <button
          type="button"
          onClick={upload}
          disabled={!saved || busy !== null || uploaded}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-primary-200 bg-white px-4 py-2 text-sm font-semibold text-primary-800 transition-colors hover:bg-primary-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "uploading" ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <UploadIcon className="h-4 w-4" aria-hidden="true" />
          )}
          {uploaded ? "Processing started" : "Upload video"}
        </button>

        <p className="text-xs text-slate-400" aria-live="polite">
          {uploaded
            ? "Analysis is running. The match page shows progress."
            : saved
              ? "Uploading starts processing straight away."
              : "Save the calibration first. Uploading begins processing immediately, so corners saved afterwards would only apply to the next run."}
        </p>
      </div>
    </div>
  );
}
