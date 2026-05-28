import { NextResponse } from "next/server";

const DASHBOARD_API_URL =
  process.env.DASHBOARD_API_URL || "http://localhost:8003";

export async function GET(
  _req: Request,
  { params }: { params: { product_id: string } }
) {
  const res = await fetch(
    `${DASHBOARD_API_URL}/api/dashboard/forecast/drift/${params.product_id}`,
    { cache: "no-store" }
  );
  const data = await res.json();
  return NextResponse.json(data);
}
