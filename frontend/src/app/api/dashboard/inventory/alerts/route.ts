import { NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function GET() {
  const res = await fetch(`${DASHBOARD_API}/api/dashboard/inventory/alerts`, {
    next: { revalidate: 0 }, // always fresh — no caching for live data
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
