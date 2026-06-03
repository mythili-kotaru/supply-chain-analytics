import { NextResponse } from "next/server";

const API_URL = process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/dashboard/inventory/all`, {
      cache: "no-store",
    });
    
    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend API returned ${res.status}` },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching inventory all:", error);
    return NextResponse.json(
      { error: "Failed to connect to Dashboard API" },
      { status: 500 }
    );
  }
}
