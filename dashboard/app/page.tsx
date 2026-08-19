import Link from "next/link";
import { Plus } from "lucide-react";
import { api } from "@/lib/api";
import { redirectIfUnauthorized } from "@/lib/guard";
import MatchCard from "@/components/MatchCard";

export default async function HomePage() {
  let matches;
  try {
    matches = await api.matches.list();
  } catch (err) {
    redirectIfUnauthorized(err);
    return (
      <main id="main-content" className="py-8">
        <div className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="text-sm font-semibold text-red-700">
            Could not reach the API
          </p>
          <p className="mt-1 text-sm text-red-600">
            Make sure the FastAPI server is running on{" "}
            <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-xs">
              {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
            </code>
          </p>
        </div>
      </main>
    );
  }

  const done = matches.filter((m) => m.processing_status === "done").length;
  const processing = matches.filter(
    (m) => m.processing_status === "processing",
  ).length;

  return (
    <main id="main-content">
      {/* Page header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Matches</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {matches.length} total
            {done > 0 && (
              <>
                {" "}
                ·{" "}
                <span className="text-emerald-600 font-medium">
                  {done} analysed
                </span>
              </>
            )}
            {processing > 0 && (
              <>
                {" "}
                ·{" "}
                <span className="text-amber-600 font-medium">
                  {processing} processing
                </span>
              </>
            )}
          </p>
        </div>
        <Link
          href="/matches/new"
          className="inline-flex items-center gap-1.5 self-start rounded-md bg-primary-800 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 sm:self-auto"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New match
        </Link>
      </div>

      {matches.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-20 text-center">
          <p className="text-sm font-medium text-slate-400">No matches yet</p>
          <p className="mt-1 text-xs text-slate-300">
            Create a match, calibrate the camera, then upload the video
          </p>
          <Link
            href="/matches/new"
            className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-primary-800 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New match
          </Link>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {matches.map((m) => (
            <MatchCard key={m.id} match={m} />
          ))}
        </div>
      )}
    </main>
  );
}
