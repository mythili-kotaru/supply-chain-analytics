import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function POST(req: NextRequest) {
  const body = await req.json();
  return forwardRequest(req, "/api/dashboard/analytics/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
