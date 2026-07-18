import { getSourceContent, StoreError } from "@/lib/server/project-store";

export const runtime = "nodejs";

export async function GET(_request: Request, context: RouteContext<"/api/projects/[projectId]/sources/[sourceId]/content">) {
  try {
    const { projectId, sourceId } = await context.params;
    const source = await getSourceContent(projectId, sourceId);
    return new Response(source.buffer, {
      headers: {
        "content-type": source.mimeType,
        "content-length": String(source.bytes),
        "cache-control": "private, max-age=3600",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    const status = error instanceof StoreError ? error.status : 500;
    return Response.json({ error: error instanceof StoreError ? error.message : "Unable to read source" }, { status });
  }
}

