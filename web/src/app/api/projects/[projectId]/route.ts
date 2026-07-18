import { getProject, StoreError } from "@/lib/server/project-store";

export const runtime = "nodejs";

export async function GET(_request: Request, context: RouteContext<"/api/projects/[projectId]">) {
  try {
    const { projectId } = await context.params;
    return Response.json(await getProject(projectId));
  } catch (error) {
    const status = error instanceof StoreError ? error.status : 500;
    return Response.json({ error: error instanceof StoreError ? error.message : "Unable to read project" }, { status });
  }
}

