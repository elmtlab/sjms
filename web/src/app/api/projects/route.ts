import { createProject, listProjects, StoreError } from "@/lib/server/project-store";

export const runtime = "nodejs";

export async function GET() {
  return Response.json({ projects: await listProjects() });
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { name?: string; audience?: string; objective?: string };
    const project = await createProject({ name: body.name ?? "", audience: body.audience ?? "", objective: body.objective ?? "" });
    return Response.json(project, { status: 201 });
  } catch (error) {
    const status = error instanceof StoreError ? error.status : 400;
    return Response.json({ error: error instanceof StoreError ? error.message : "Invalid project request" }, { status });
  }
}

