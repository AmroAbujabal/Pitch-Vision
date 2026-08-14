import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import PitchControlBar from "@/components/PitchControlBar";
import PlayerTable from "@/components/PlayerTable";
import StatusBadge from "@/components/StatusBadge";

interface Props {
  params: { id: string };
}

// ── KPI card ─────────────────────────────────────────────────
function KpiCard({
  label,
  homeValue,
  awayValue,
  homeLabel,
  awayLabel,
}: {
  label: string;
  homeValue: string;
  awayValue: string;
  homeLabel: string;
  awayLabel: string;
}) {
  return (
    <div className="card flex flex-col gap-3">
      <p className="kpi-label">{label}</p>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="mb-0.5 text-2xs font-semibold uppercase tracking-wider text-home/70">
            {homeLabel}
          </p>
          <p className="kpi-value text-home">{homeValue}</p>
        </div>
        <div className="text-right">
          <p className="mb-0.5 text-2xs font-semibold uppercase tracking-wider text-away/70">
            {awayLabel}
          </p>
          <p className="kpi-value text-away">{awayValue}</p>
        </div>
      </div>
    </div>
  );
}

// Formation is null before the match is processed, and "unknown" when it has no
// pitch calibration or too few tracked players. A coach should see the gap
// rather than a guessed shape.
function formatFormation(value: string | null): string {
  if (!value) return "—";
  return value === "unknown" ? "Unknown" : value;
}

// ── Page ─────────────────────────────────────────────────────
export default async function MatchDetailPage({ params }: Props) {
  let summary, players;
  try {
    [summary, players] = await Promise.all([
      api.matches.summary(params.id),
      api.matches.players(params.id),
    ]);
  } catch {
    return (
      <main id="main-content" className="py-8">
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm font-semibold text-red-700">
            Match not found or API unreachable
          </p>
          <Link
            href="/"
            className="mt-2 inline-block text-sm text-red-600 underline underline-offset-2"
          >
            ← Back to matches
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main id="main-content" className="space-y-5">
      {/* Breadcrumb */}
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-1.5 text-xs text-slate-400"
      >
        <Link href="/" className="hover:text-slate-700 transition-colors">
          Matches
        </Link>
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
        <span className="text-slate-700 font-medium">
          {summary.home_team} vs {summary.away_team}
        </span>
      </nav>

      {/* Match header card */}
      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <StatusBadge status={summary.processing_status} />
            <span className="text-2xs font-medium text-slate-400">
              {summary.player_count} players tracked
            </span>
          </div>
        </div>

        {/* Match title */}
        <h1 className="mb-5 text-lg font-bold leading-tight text-slate-900">
          <span className="text-home">{summary.home_team}</span>
          <span className="mx-2 font-normal text-slate-300">vs</span>
          <span className="text-away">{summary.away_team}</span>
        </h1>

        {/* Pitch control bar */}
        <PitchControlBar
          homePct={summary.home_pitch_control_pct}
          awayPct={summary.away_pitch_control_pct}
          homeTeam={summary.home_team}
          awayTeam={summary.away_team}
        />
      </div>

      {/* KPI grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Formation"
          homeValue={formatFormation(summary.home_formation)}
          awayValue={formatFormation(summary.away_formation)}
          homeLabel={summary.home_team}
          awayLabel={summary.away_team}
        />
        <KpiCard
          label="Top Speed"
          homeValue={`${summary.home_top_speed_ms.toFixed(1)}`}
          awayValue={`${summary.away_top_speed_ms.toFixed(1)}`}
          homeLabel={summary.home_team}
          awayLabel={summary.away_team}
        />
        <KpiCard
          label="Press Count"
          homeValue={String(summary.home_press_count)}
          awayValue={String(summary.away_press_count)}
          homeLabel={summary.home_team}
          awayLabel={summary.away_team}
        />
        <div className="card flex flex-col gap-3">
          <p className="kpi-label">Players Tracked</p>
          <p className="kpi-value text-slate-800">{summary.player_count}</p>
        </div>
      </div>

      {/* Player table */}
      <section aria-labelledby="player-table-heading">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="player-table-heading" className="section-title">
            Player breakdown
          </h2>
          <span className="text-2xs text-slate-400">
            Click any column to sort
          </span>
        </div>
        {players.length === 0 ? (
          <div className="card py-12 text-center">
            <p className="text-sm text-slate-400">
              No player data available yet
            </p>
          </div>
        ) : (
          <PlayerTable players={players} />
        )}
      </section>
    </main>
  );
}
