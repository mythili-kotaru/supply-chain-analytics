import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function GET(req: NextRequest) {
  return forwardRequest(req, "/api/dashboard/simulation/scenarios", {
    method: "GET",
  });
}

export async function POST(req: NextRequest) {
  return forwardRequest(req, "/api/dashboard/simulation/scenarios", {
    method: "POST",
  });
}
