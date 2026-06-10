import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(
  req: NextRequest,
  { params }: { params: { product_id: string } }
) {
  return forwardRequest(req, `/api/dashboard/forecast/drift/${params.product_id}`);
}
