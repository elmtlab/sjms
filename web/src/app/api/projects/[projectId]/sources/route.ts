import { addFileSource, addUrlSource, StoreError } from "@/lib/server/project-store";

export const runtime = "nodejs";

export async function POST(request: Request, context: RouteContext<"/api/projects/[projectId]/sources">) {
  try {
    const { projectId } = await context.params;
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const body = await request.json() as { kind?: string; url?: string };
      if (body.kind !== "url" || !body.url) throw new StoreError("A URL source is required");
      return Response.json(await addUrlSource(projectId, body.url), { status: 201 });
    }

    const form = await request.formData();
    const kind = form.get("kind");
    const file = form.get("file");
    if ((kind !== "screenshot" && kind !== "recording") || !(file instanceof File)) throw new StoreError("A screenshot or recording file is required");
    return Response.json(await addFileSource(projectId, kind, file), { status: 201 });
  } catch (error) {
    const status = error instanceof StoreError ? error.status : 500;
    return Response.json({ error: error instanceof StoreError ? error.message : "Unable to store source" }, { status });
  }
}

