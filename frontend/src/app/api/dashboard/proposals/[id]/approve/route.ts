import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const res = await fetch(
    `${DASHBOARD_API}/api/dashboard/proposals/${params.id}/approve`,
    { method: "POST" }
  );
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
