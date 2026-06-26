import { NextRequest } from "next/server";
import { forwardRequest } from "@/lib/proxy";

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return forwardRequest(
    req,
    `/api/dashboard/simulation/scenarios/${params.id}`,
    { method: "DELETE" }
  );
}
