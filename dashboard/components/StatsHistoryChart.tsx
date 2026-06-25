"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  TooltipProps,
} from "recharts";
import type { PlayerStats } from "@/lib/types";

interface Props {
  stats: PlayerStats[];
}

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 shadow-lg text-xs">
      <p className="mb-1.5 font-semibold text-slate-700">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 py-0.5">
          <span
            className="h-2 w-2 rounded-full flex-shrink-0"
            style={{ background: entry.color }}
            aria-hidden="true"
          />
          <span className="text-slate-500">{entry.name}:</span>
          <span className="font-mono font-semibold text-slate-800">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function StatsHistoryChart({ stats }: Props) {
  const data = [...stats]
    .reverse()
    .slice(-8)
    .map((s) => ({
      match: `${(s.home_team ?? '???').slice(0, 3)} v ${(s.away_team ?? '???').slice(0, 3)}`,
      "Distance (m)": s.distance_covered_m ?? 0,
      Sprints:        s.sprint_count ?? 0,
      Presses:        s.press_count  ?? 0,
    }));

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg bg-slate-50">
        <p className="text-sm text-slate-400">No match history yet</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 0 }} barGap={3}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
        <XAxis
          dataKey="match"
          tick={{ fontSize: 11, fill: "#94A3B8", fontFamily: "'Fira Code', monospace" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="distance"
          orientation="left"
          tick={{ fontSize: 11, fill: "#94A3B8", fontFamily: "'Fira Code', monospace" }}
          axisLine={false}
          tickLine={false}
          width={52}
        />
        <YAxis
          yAxisId="small"
          orientation="right"
          tick={{ fontSize: 11, fill: "#94A3B8", fontFamily: "'Fira Code', monospace" }}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(30,64,175,0.04)" }} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: "12px", color: "#64748B" }}
          iconType="circle"
          iconSize={8}
        />
        <Bar
          yAxisId="distance"
          dataKey="Distance (m)"
          fill="#1E40AF"
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
        />
        <Bar
          yAxisId="small"
          dataKey="Sprints"
          fill="#3B82F6"
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
        />
        <Bar
          yAxisId="small"
          dataKey="Presses"
          fill="#D97706"
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
