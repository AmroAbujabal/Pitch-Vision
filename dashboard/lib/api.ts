import type { MatchListItem, MatchSummary, MatchPlayer, PlayerStats, PlayerProfile, PlayerHeatmap, PlayerPrediction } from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    // Disable Next.js data cache so dashboards always show fresh data.
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status} at ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  matches: {
    /** All matches for an academy, newest first. */
    list: (academyId: string) =>
      apiFetch<MatchListItem[]>(`/api/v1/matches/?academy_id=${academyId}`),

    /** Aggregated match-level stats for the summary card. */
    summary: (matchId: string) =>
      apiFetch<MatchSummary>(`/api/v1/matches/${matchId}/summary`),

    /** All players and their stats for a match. */
    players: (matchId: string) =>
      apiFetch<MatchPlayer[]>(`/api/v1/matches/${matchId}/players`),
  },

  players: {
    /** Full stats history for one player, newest match first. */
    stats: (playerId: string) =>
      apiFetch<PlayerStats[]>(`/api/v1/players/${playerId}/stats`),

    /** Full profile: bio + latest match stats + development trend. */
    profile: (playerId: string) =>
      apiFetch<PlayerProfile>(`/api/v1/players/${playerId}/profile`),

    /** Heatmap grid data for a player in a specific match. */
    heatmap: (playerId: string, matchId: string) =>
      apiFetch<PlayerHeatmap>(`/api/v1/players/${playerId}/heatmap?match_id=${matchId}`),

    /** Predicted development score for the coming week. */
    prediction: (playerId: string) =>
      apiFetch<PlayerPrediction>(`/api/v1/players/${playerId}/prediction`),
  },
};
