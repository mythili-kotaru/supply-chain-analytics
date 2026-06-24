import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  return forwardRequest(req, "/api/dashboard/sourcing/scorecard");
}
