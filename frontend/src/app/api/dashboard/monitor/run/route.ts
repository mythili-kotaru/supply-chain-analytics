import { NextResponse } from "next/server";

const API_URL = process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function POST() {
  try {
    const res = await fetch(`${API_URL}/api/dashboard/monitor/run`, {
      method: "POST",
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error("Error triggering monitor run:", error);
    return NextResponse.json(
      { error: "Failed to connect to Dashboard API" },
      { status: 500 }
    );
  }
}
