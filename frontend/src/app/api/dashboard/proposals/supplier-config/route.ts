import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  return forwardRequest(request, "/api/dashboard/proposals/supplier-config");
}
