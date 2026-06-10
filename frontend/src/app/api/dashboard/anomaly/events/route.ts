import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const params = new URLSearchParams();
  if (searchParams.get("unacked_only")) params.set("unacked_only", "true");
  if (searchParams.get("severity")) params.set("severity", searchParams.get("severity")!);
  
  const queryStr = params.toString();
  const path = `/api/dashboard/anomaly/events${queryStr ? `?${queryStr}` : ""}`;
  return forwardRequest(req, path);
}
