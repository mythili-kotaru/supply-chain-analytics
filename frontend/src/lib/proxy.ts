import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_API = process.env.DASHBOARD_API_URL ?? "http://localhost:8003";

export async function forwardRequest(
  request: NextRequest,
  path: string,
  options?: RequestInit
) {
  const role = request.headers.get("x-role") || "analyst";
  const auth = request.headers.get("authorization");
  const contentType = request.headers.get("content-type");
  const headers = new Headers(options?.headers);
  headers.set("x-role", role);
  if (auth) {
    headers.set("authorization", auth);
  }
  if (contentType) {
    headers.set("content-type", contentType);
  }

  try {
    const res = await fetch(`${DASHBOARD_API}${path}`, {
      ...options,
      headers,
      next: { revalidate: 0 }
    });

    const contentType = res.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    } else {
      const data = await res.text();
      return new NextResponse(data, { status: res.status });
    }
  } catch (error) {
    console.error(`Error forwarding request to ${path}:`, error);
    return NextResponse.json(
      { error: `Internal server error: ${error instanceof Error ? error.message : String(error)}` },
      { status: 500 }
    );
  }
}
