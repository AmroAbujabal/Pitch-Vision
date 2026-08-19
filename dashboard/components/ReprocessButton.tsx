"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

/**
 * Re-run the pipeline on a match whose video is already uploaded.
 *
 * Calibration only takes effect on the next run, so a coach who uploaded
 * before marking the corners needs an explicit way to ask for another pass.
 * `router.refresh()` re-renders the server page so the status badge picks up
 * "processing" without a reload.
 */
export default function ReprocessButton({ matchId }: { matchId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reprocess() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/matches/${matchId}/reprocess`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.json();
        setError(body.error ?? "Could not start the re-run.");
        return;
      }
      router.refresh();
    } catch {
      setError("Could not reach the dashboard server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 space-y-1.5">
      <button
        type="button"
        onClick={reprocess}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-xs font-medium text-amber-900 transition-colors hover:bg-amber-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RefreshCw
          className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`}
          aria-hidden="true"
        />
        {busy ? "Starting…" : "Re-run analysis"}
      </button>
      {error && (
        <p role="alert" className="text-2xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
