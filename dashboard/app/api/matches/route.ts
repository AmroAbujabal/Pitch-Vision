import { forward } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.text();
  return forward("/api/v1/matches/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
