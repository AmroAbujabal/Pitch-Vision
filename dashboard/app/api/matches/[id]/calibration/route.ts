import { badId, forward, isUuid } from "@/lib/proxy";

export async function PUT(
  request: Request,
  { params }: { params: { id: string } },
) {
  if (!isUuid(params.id)) return badId();
  const body = await request.text();
  return forward(`/api/v1/matches/${params.id}/calibration`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
