import { badId, forward, isUuid } from "@/lib/proxy";

/** Re-run the pipeline on the video already uploaded for this match. */
export async function POST(
  _request: Request,
  { params }: { params: { id: string } },
) {
  if (!isUuid(params.id)) return badId();

  return forward(`/api/v1/matches/${params.id}/reprocess`, { method: "POST" });
}
