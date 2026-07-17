import "server-only";

import { ProjectDTO, saveUnderstanding } from "@/lib/server/project-store";

export type ProductUnderstanding = {
  schemaVersion: "0.1";
  projectId: string;
  revision: number;
  audience: string;
  objective: "feature_education";
  problem: string;
  valueProposition: string;
  claims: Array<{
    claimId: string;
    text: string;
    confidence: number;
    status: "proposed";
    evidence: Array<{ sourceId: string; artifactId: null; locator: string; excerpt: string }>;
  }>;
  features: Array<{ featureId: string; name: string; benefit: string; claimIds: string[] }>;
  provider: "mock";
};

function mockUnderstanding(project: ProjectDTO): ProductUnderstanding {
  const primary = project.sources[0];
  const evidence = primary ? [{ sourceId: primary.sourceId, artifactId: null, locator: primary.kind === "url" ? "page" : "full-frame", excerpt: primary.name }] : [];
  return {
    schemaVersion: "0.1",
    projectId: project.projectId,
    revision: 1,
    audience: project.audience || "正在发布新功能的 SaaS 团队",
    objective: "feature_education",
    problem: "产品已经上线，却没有时间制作清晰的功能介绍视频。",
    valueProposition: "从网址、截图或录屏自动生成可修改的产品介绍视频。",
    claims: [
      { claimId: "claim_problem", text: "脚本、录屏、剪辑分散在多个工具，制作一条功能视频需要数天。", confidence: 0.9, status: "proposed", evidence },
      { claimId: "claim_value", text: "AI 理解产品素材，生成可以直接修改的脚本、镜头、旁白和字幕。", confidence: 0.94, status: "proposed", evidence },
      { claimId: "claim_output", text: "同一个产品故事可以输出横版和竖版视频。", confidence: 0.92, status: "proposed", evidence },
    ],
    features: [
      { featureId: "feature_understand", name: "素材理解", benefit: "从产品素材中提炼核心价值与证据", claimIds: ["claim_value"] },
      { featureId: "feature_outputs", name: "多画幅输出", benefit: "同一个故事快速适配不同发布渠道", claimIds: ["claim_output"] },
    ],
    provider: "mock",
  };
}

export async function analyzeProject(project: ProjectDTO) {
  if (project.sources.length === 0) throw new Error("At least one source is required");
  const understanding = mockUnderstanding(project);
  await saveUnderstanding(project.projectId, understanding);
  return understanding;
}

