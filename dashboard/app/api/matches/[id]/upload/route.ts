import { NextResponse } from "next/server";
import { badId, forward, isUuid } from "@/lib/proxy";

/**
 * Stream the video through to the API rather than buffering it.
 *
 * Match footage is routinely gigabytes; reading it into memory here would put
 * the whole file in the Node process for no reason. `duplex: "half"` is
 * required by undici whenever the body is a stream.
 */
export async function POST(
  request: Request,
  { params }: { params: { id: string } },
) {
  if (!isUuid(params.id)) return badId();

  const contentType = request.headers.get("content-type");
  if (!contentType?.startsWith("multipart/form-data")) {
    return NextResponse.json(
      { error: "Expected a multipart upload" },
      { status: 400 },
    );
  }

  return forward(`/api/v1/matches/${params.id}/upload-video`, {
    method: "POST",
    headers: { "Content-Type": contentType },
    body: request.body,
    duplex: "half",
  } as RequestInit);
}
