import { analyzeProject } from "@/lib/server/understanding";
import { getProject, StoreError } from "@/lib/server/project-store";

export const runtime = "nodejs";

export async function POST(_request: Request, context: RouteContext<"/api/projects/[projectId]/analysis">) {
  try {
    const { projectId } = await context.params;
    const understanding = await analyzeProject(await getProject(projectId));
    return Response.json(understanding);
  } catch (error) {
    const status = error instanceof StoreError ? error.status : 400;
    return Response.json({ error: error instanceof StoreError ? error.message : "Unable to analyze project" }, { status });
  }
}

