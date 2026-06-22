import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function POST(req: NextRequest) {
  return forwardRequest(req, "/api/dashboard/forecast/confluence-report", {
    method: "POST",
  });
}
