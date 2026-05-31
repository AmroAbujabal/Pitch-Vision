import Link from "next/link";
import { ChevronRight, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { api } from "@/lib/api";
import type { DevelopmentScore, PlayerPrediction } from "@/lib/types";
import StatsHistoryChart from "@/components/StatsHistoryChart";

interface Props {
  params: { id: string };
}

function fmtDist(v: number | null) { return v != null ? `${Math.round(v)} m`       : "—"; }
function fmtSpd (v: number | null) { return v != null ? `${v.toFixed(2)} m/s`      : "—"; }
function fmtPct (v: number | null) { return v != null ? `${(v * 100).toFixed(1)}%` : "—"; }

function MetricPill({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-3">
      <p className="kpi-label">{label}</p>
      <p
        className="text-xl font-bold tabular-nums leading-none text-slate-800"
        style={{ fontFamily: "'Fira Code', monospace" }}
      >
        {value ?? "—"}
      </p>
    </div>
  );
}

function TrendRow({ score }: { score: DevelopmentScore }) {
  const week = new Date(score.week_start).toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
  return (
    <tr>
      <td className="whitespace-nowrap text-slate-700">{week}</td>
      <td className="tabular-nums font-semibold text-slate-900">{score.overall_score.toFixed(1)}</td>
      <td className="tabular-nums">{score.physical_score?.toFixed(1) ?? "—"}</td>
      <td className="tabular-nums">{score.tactical_score?.toFixed(1) ?? "—"}</td>
      <td className="tabular-nums">{score.technical_score?.toFixed(1) ?? "—"}</td>
    </tr>
  );
}

const TREND_ICON = {
  improving: TrendingUp,
  stable:    Minus,
  declining: TrendingDown,
} as const;

const TREND_COLOUR = {
  improving: "text-emerald-600",
  stable:    "text-slate-500",
  declining: "text-red-500",
} as const;

function PredictionCard({ prediction }: { prediction: PlayerPrediction }) {
  const Icon = TREND_ICON[prediction.trend];
  const trendColour = TREND_COLOUR[prediction.trend];
  const isFallback = prediction.confidence < 0.5;

  return (
    <section aria-labelledby="prediction-heading" className="card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="prediction-heading" className="section-title">Next week prediction</h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Week of {new Date(prediction.week).toLocaleDateString("en-GB", {
              day: "2-digit", month: "short", year: "numeric",
            })}
          </p>
        </div>
        {isFallback && (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-2xs font-medium text-slate-500">
            estimate
          </span>
        )}
      </div>

      <div className="mt-4 flex items-end gap-6">
        {/* Predicted score */}
        <div>
          <p className="kpi-label mb-1">Predicted score</p>
          <p
            className="text-4xl font-bold tabular-nums leading-none text-slate-900"
            style={{ fontFamily: "'Fira Code', monospace" }}
          >
            {prediction.predicted_score.toFixed(1)}
            <span className="ml-1 text-base font-normal text-slate-400">/10</span>
          </p>
        </div>

        {/* Trend */}
        <div className={`flex items-center gap-1.5 pb-1 ${trendColour}`}>
          <Icon className="h-5 w-5" aria-hidden="true" />
          <span className="text-sm font-semibold capitalize">{prediction.trend}</span>
        </div>

        {/* vs current */}
        <div className="pb-1">
          <p className="kpi-label mb-1">Current</p>
          <p
            className="text-lg font-semibold tabular-nums text-slate-500"
            style={{ fontFamily: "'Fira Code', monospace" }}
          >
            {prediction.current_score.toFixed(1)}
          </p>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-2xs text-slate-400 mb-1">
          <span>Model confidence</span>
          <span>{Math.round(prediction.confidence * 100)}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-slate-100">
          <div
            className={`h-1.5 rounded-full transition-all ${isFallback ? "bg-slate-300" : "bg-primary-500"}`}
            style={{ width: `${prediction.confidence * 100}%` }}
            role="meter"
            aria-valuenow={Math.round(prediction.confidence * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Model confidence"
          />
        </div>
        {isFallback && (
          <p className="mt-1.5 text-2xs text-slate-400">
            Using rolling average — train a model once match data accumulates.
          </p>
        )}
      </div>
    </section>
  );
}

export default async function PlayerProfilePage({ params }: Props) {
  let profile;
  let statsHistory;
  let prediction: PlayerPrediction | null = null;

  try {
    [profile, statsHistory] = await Promise.all([
      api.players.profile(params.id),
      api.players.stats(params.id),
    ]);
  } catch {
    return (
      <main id="main-content" className="py-8">
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm font-semibold text-red-700">Player not found or API unreachable</p>
          <Link href="/" className="mt-2 inline-block text-sm text-red-600 underline underline-offset-2">
            ← Back to matches
          </Link>
        </div>
      </main>
    );
  }

  // Prediction is optional — silently skip if not enough history yet
  try {
    prediction = await api.players.prediction(params.id);
  } catch {
    // 422 = not enough history; any other error → degrade gracefully
  }

  const latest = profile.latest_stats;

  return (
    <main id="main-content" className="space-y-5">

      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-slate-400">
        <Link href="/" className="hover:text-slate-700 transition-colors">Matches</Link>
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
        <span className="text-slate-700 font-medium">Player Profile</span>
      </nav>

      {/* Profile header */}
      <div className="card flex items-center gap-4">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white"
          style={{ background: "linear-gradient(135deg, #1E40AF 0%, #3B82F6 100%)" }}
          aria-hidden="true"
        >
          <span
            className="text-base font-bold"
            style={{ fontFamily: "'Fira Code', monospace" }}
          >
            {profile.jersey_number != null ? `#${profile.jersey_number}` : "#"}
          </span>
        </div>
        <div className="min-w-0">
          <h1 className="text-base font-bold text-slate-900 truncate">{profile.name}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            <span className="font-semibold text-slate-700">{profile.position}</span>
            <span className="mx-1.5 text-slate-300">·</span>
            <span
              className="tabular-nums font-semibold text-slate-700"
              style={{ fontFamily: "'Fira Code', monospace" }}
            >
              {statsHistory.length}
            </span>
            {" "}match{statsHistory.length !== 1 ? "es" : ""} on record
          </p>
        </div>
      </div>

      {/* Prediction card — shown whenever we have enough history */}
      {prediction && <PredictionCard prediction={prediction} />}

      {/* Latest match snapshot */}
      {latest && (
        <section aria-labelledby="latest-heading">
          <div className="mb-3">
            <h2 id="latest-heading" className="section-title">Latest match</h2>
            {latest.home_team && latest.away_team && (
              <p className="mt-0.5 text-xs text-slate-500">
                <span className="font-semibold text-home">{latest.home_team}</span>
                <span className="mx-1.5 text-slate-300">vs</span>
                <span className="font-semibold text-away">{latest.away_team}</span>
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MetricPill label="Distance"      value={fmtDist(latest.distance_covered_m)} />
            <MetricPill label="Top speed"     value={fmtSpd(latest.top_speed_ms)} />
            <MetricPill label="Avg speed"     value={fmtSpd(latest.avg_speed_ms)} />
            <MetricPill label="Sprints"       value={latest.sprint_count} />
            <MetricPill label="Hi-int. runs"  value={latest.hi_run_count} />
            <MetricPill label="Press count"   value={latest.press_count} />
            <MetricPill label="Press success" value={fmtPct(latest.press_success_rate)} />
            <MetricPill label="Pitch control" value={fmtPct(latest.pitch_control_contribution)} />
          </div>
        </section>
      )}

      {/* Development trend */}
      {profile.development_trend.length > 0 && (
        <section aria-labelledby="trend-heading">
          <h2 id="trend-heading" className="section-title mb-3">Development trend</h2>
          <div className="overflow-x-auto rounded-[10px] border border-slate-200">
            <table className="data-table" aria-label="Weekly development scores">
              <thead>
                <tr>
                  {["Week", "Overall", "Physical", "Tactical", "Technical"].map(h => (
                    <th key={h} className="cursor-default">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {profile.development_trend.map((s, i) => (
                  <TrendRow key={i} score={s} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* History chart */}
      <section aria-labelledby="chart-heading" className="card">
        <h2 id="chart-heading" className="section-title mb-4">Match history</h2>
        <StatsHistoryChart stats={statsHistory} />
        <p className="mt-3 text-center text-2xs text-slate-400">
          Distance (navy, left axis) · Sprints &amp; Presses (right axis) · last 8 matches
        </p>
      </section>

      {/* Full history table */}
      <section aria-labelledby="history-table-heading">
        <h2 id="history-table-heading" className="section-title mb-3">All matches</h2>
        <div className="overflow-x-auto rounded-[10px] border border-slate-200">
          <table className="data-table" aria-label="All match statistics">
            <thead>
              <tr>
                {["Match", "Team", "Distance", "Top Spd", "Sprints", "Presses", "Press %", "Pitch Ctrl"].map(
                  h => <th key={h} className="cursor-default">{h}</th>
                )}
              </tr>
            </thead>
            <tbody>
              {statsHistory.map(s => (
                <tr key={s.match_id}>
                  <td className="font-medium text-slate-900 whitespace-nowrap">
                    {s.match_id ? (
                      <Link
                        href={`/matches/${s.match_id}`}
                        className="hover:text-primary-700 hover:underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 rounded"
                      >
                        {s.home_team ?? "?"} vs {s.away_team ?? "?"}
                      </Link>
                    ) : "—"}
                  </td>
                  <td>
                    <span className={s.team === "home" ? "team-pill-home" : "team-pill-away"}>
                      {s.team}
                    </span>
                  </td>
                  <td className="tabular-nums">{fmtDist(s.distance_covered_m)}</td>
                  <td className="tabular-nums">{fmtSpd(s.top_speed_ms)}</td>
                  <td className="tabular-nums">{s.sprint_count ?? "—"}</td>
                  <td className="tabular-nums">{s.press_count  ?? "—"}</td>
                  <td className="tabular-nums">{fmtPct(s.press_success_rate)}</td>
                  <td className="tabular-nums">{fmtPct(s.pitch_control_contribution)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
