import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status");

  const url = new URL(`${DASHBOARD_API}/api/dashboard/proposals`);
  if (status) url.searchParams.set("status", status);

  const res = await fetch(url.toString(), { next: { revalidate: 0 } });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
