import { NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function GET() {
  const res = await fetch(`${DASHBOARD_API}/api/dashboard/stats`, {
    next: { revalidate: 0 },
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
