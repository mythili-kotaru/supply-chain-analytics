import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status");
  const path = `/api/dashboard/proposals${status ? `?status=${status}` : ""}`;
  return forwardRequest(request, path);
}
