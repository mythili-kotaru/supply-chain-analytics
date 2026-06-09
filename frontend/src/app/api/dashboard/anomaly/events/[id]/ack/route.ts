import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return forwardRequest(
    req,
    `/api/dashboard/anomaly/events/${params.id}/ack`,
    { method: "POST" }
  );
}
