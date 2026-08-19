"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";

export default function NewMatchPage() {
  const router = useRouter();
  const [homeTeam, setHomeTeam] = useState("");
  const [awayTeam, setAwayTeam] = useState("");
  const [matchDate, setMatchDate] = useState("");
  const [venue, setVenue] = useState("");
  // Every physical metric divides by this (scripts/run_pipeline.py), so
  // leaving the API's 25.0 default on 30fps phone footage overstates distance
  // and speed by about 20% with nothing on screen to say so.
  const [fps, setFps] = useState("25");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          home_team: homeTeam.trim(),
          away_team: awayTeam.trim(),
          match_date: matchDate ? new Date(matchDate).toISOString() : null,
          venue: venue.trim() || null,
          fps: Number(fps),
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Could not create the match.");
        return;
      }
      // Straight to calibration: the pipeline starts the moment a video is
      // uploaded, so the corners have to be set before that happens.
      router.push(`/matches/${body.id}/calibrate`);
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main id="main-content" className="mx-auto max-w-lg space-y-5">
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-1.5 text-xs text-slate-400"
      >
        <Link href="/" className="transition-colors hover:text-slate-700">
          Matches
        </Link>
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
        <span className="font-medium text-slate-700">New match</span>
      </nav>

      <div className="card">
        <h1 className="mb-1 text-base font-semibold text-slate-800">
          New match
        </h1>
        <p className="mb-5 text-sm text-slate-500">
          Camera calibration comes next, before the video is uploaded.
        </p>

        {error && (
          <p
            role="alert"
            className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {error}
          </p>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <Field
            id="home-team"
            label="Home team"
            required
            value={homeTeam}
            onChange={setHomeTeam}
          />
          <Field
            id="away-team"
            label="Away team"
            required
            value={awayTeam}
            onChange={setAwayTeam}
          />
          <Field
            id="match-date"
            label="Date"
            type="date"
            value={matchDate}
            onChange={setMatchDate}
          />
          <Field
            id="venue"
            label="Venue"
            value={venue}
            onChange={setVenue}
            help="Optional"
          />

          <div className="flex flex-col gap-2">
            <label htmlFor="fps" className="text-sm font-medium text-slate-700">
              Camera frame rate
            </label>
            <select
              id="fps"
              value={fps}
              onChange={(e) => setFps(e.target.value)}
              aria-describedby="fps-help"
              className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            >
              <option value="25">25 fps</option>
              <option value="30">30 fps (most phones)</option>
              <option value="50">50 fps</option>
              <option value="60">60 fps</option>
            </select>
            <p id="fps-help" className="text-xs text-slate-400">
              Distance and speed are calculated from this. Check your camera
              settings if you are unsure.
            </p>
          </div>

          <button
            type="submit"
            disabled={submitting || !homeTeam.trim() || !awayTeam.trim()}
            className="mt-1 inline-flex items-center justify-center gap-2 rounded-md bg-primary-800 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {submitting ? "Creating" : "Create and calibrate"}
          </button>
        </form>
      </div>
    </main>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  required = false,
  help,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  help?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        {label}
        {required && (
          <span className="ml-1 text-red-600" aria-hidden="true">
            *
          </span>
        )}
      </label>
      <input
        id={id}
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={help ? `${id}-help` : undefined}
        className="rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      />
      {help && (
        <p id={`${id}-help`} className="text-xs text-slate-400">
          {help}
        </p>
      )}
    </div>
  );
}
