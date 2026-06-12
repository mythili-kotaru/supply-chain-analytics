import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const role = req.headers.get("x-role") || "analyst";
  const auth = req.headers.get("authorization");

  const headers = new Headers();
  headers.set("x-role", role);
  if (auth) {
    headers.set("authorization", auth);
  }

  try {
    const res = await fetch(`${DASHBOARD_API}/api/dashboard/proposals/${params.id}/approve/stream`, {
      method: "POST",
      headers,
      next: { revalidate: 0 },
    });

    if (!res.body) {
      return new NextResponse("No body", { status: 500 });
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
    });
  } catch (error) {
    console.error("Error in Next.js approve/stream route proxy:", error);
    return NextResponse.json(
      { error: `Internal server error: ${error instanceof Error ? error.message : String(error)}` },
      { status: 500 }
    );
  }
}
