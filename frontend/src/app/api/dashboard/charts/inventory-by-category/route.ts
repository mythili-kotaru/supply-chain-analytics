import { NextResponse } from "next/server";
const API_URL = process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/dashboard/charts/inventory-by-category`, { cache: "no-store" });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: "Failed to connect to Dashboard API" }, { status: 500 });
  }
}
