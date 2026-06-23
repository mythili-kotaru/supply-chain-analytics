import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function POST(req: NextRequest) {
  const role = req.headers.get("x-role") || "analyst";
  const auth = req.headers.get("authorization");

  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  headers.set("x-role", role);
  if (auth) {
    headers.set("authorization", auth);
  }

  try {
    const body = await req.json();

    const res = await fetch(`${DASHBOARD_API}/api/dashboard/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      next: { revalidate: 0 },
    });

    if (!res.body) {
      return new NextResponse("No body", { status: 500 });
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
      },
    });
  } catch (error) {
    console.error("Error in Next.js chat/stream route proxy:", error);
    return NextResponse.json(
      { error: `Internal server error: ${error instanceof Error ? error.message : String(error)}` },
      { status: 500 }
    );
  }
}
