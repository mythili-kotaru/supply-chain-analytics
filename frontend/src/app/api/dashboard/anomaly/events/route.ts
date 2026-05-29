import { NextResponse } from "next/server";

const DASHBOARD_API_URL =
  process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const params = new URLSearchParams();
  if (searchParams.get("unacked_only")) params.set("unacked_only", "true");
  if (searchParams.get("severity")) params.set("severity", searchParams.get("severity")!);

  const res = await fetch(
    `${DASHBOARD_API_URL}/api/dashboard/anomaly/events?${params}`,
    { cache: "no-store" }
  );
  const data = await res.json();
  return NextResponse.json(data);
}
