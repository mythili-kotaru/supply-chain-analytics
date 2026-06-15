import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(request: NextRequest) {
  return forwardRequest(request, "/api/dashboard/suppliers");
}
