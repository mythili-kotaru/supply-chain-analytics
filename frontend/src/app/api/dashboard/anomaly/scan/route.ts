import { NextResponse } from "next/server";

const DASHBOARD_API_URL =
  process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function POST() {
  const res = await fetch(
    `${DASHBOARD_API_URL}/api/dashboard/anomaly/scan`,
    { method: "POST", cache: "no-store" }
  );
  const data = await res.json();
  return NextResponse.json(data);
}
