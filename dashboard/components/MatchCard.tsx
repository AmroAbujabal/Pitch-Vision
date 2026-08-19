import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { MatchListItem } from "@/lib/types";
import { formatDay, formatInstant, isoDay, isoInstant } from "@/lib/dates";
import StatusBadge from "./StatusBadge";

interface Props {
  match: MatchListItem;
}

export default function MatchCard({ match }: Props) {
  const isProcessable = match.processing_status === "done";

  // A chosen match day is a calendar date; the upload time it falls back to is
  // an instant. See lib/dates.ts for why that distinction matters.
  const day = match.match_date;
  const shownDate = day ? formatDay(day) : formatInstant(match.created_at);
  const machineDate = day ? isoDay(day) : isoInstant(match.created_at);

  return (
    <Link
      href={`/matches/${match.id}`}
      className="card card-hover group flex flex-col gap-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 rounded-[10px]"
      aria-label={`${match.home_team} vs ${match.away_team}, ${match.processing_status}`}
    >
      {/* Status + date row */}
      <div className="flex items-center justify-between">
        <StatusBadge status={match.processing_status} />
        <time
          dateTime={machineDate}
          className="text-2xs font-medium text-slate-400 tabular-nums"
        >
          {shownDate}
        </time>
      </div>

      {/* Match identity */}
      <div className="flex items-center gap-2">
        {/* Home team */}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-home leading-tight">
            {match.home_team}
          </p>
          <p className="mt-0.5 text-2xs font-medium uppercase tracking-wider text-slate-400">
            Home
          </p>
        </div>

        {/* Divider */}
        <span className="shrink-0 rounded bg-slate-100 px-2 py-1 text-2xs font-bold text-slate-400 tabular-nums">
          vs
        </span>

        {/* Away team */}
        <div className="min-w-0 flex-1 text-right">
          <p className="truncate text-sm font-semibold text-away leading-tight">
            {match.away_team}
          </p>
          <p className="mt-0.5 text-2xs font-medium uppercase tracking-wider text-slate-400">
            Away
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end border-t border-slate-100 pt-3">
        <span className="flex items-center gap-1 text-2xs font-semibold text-slate-400 transition-colors duration-150 group-hover:text-primary-700">
          {isProcessable ? "View analytics" : "View match"}
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
        </span>
      </div>
    </Link>
  );
}
