export type SourceKind = "screenshot" | "url" | "recording";

export type ProjectSource = {
  id: string;
  kind: SourceKind;
  name: string;
  meta: string;
  preview?: string;
  file?: File;
};

export type ProductBrief = {
  audience: string;
  objective: string;
  problem: string;
  value: string;
};

export type Claim = {
  id: string;
  title: string;
  detail: string;
  evidence: string;
  confirmed: boolean;
  tone: "coral" | "green" | "cyan";
};

export type StoryScene = {
  id: string;
  purpose: string;
  narration: string;
  visual: string;
  duration: string;
};

export const initialBrief: ProductBrief = {
  audience: "正在发布新功能的 SaaS 团队",
  objective: "让用户在 30 秒内理解核心价值",
  problem: "产品已经上线，却没有时间制作清晰的功能介绍视频。",
  value: "从网址、截图或录屏自动生成可修改的产品介绍视频。",
};

export const initialClaims: Claim[] = [
  {
    id: "claim-problem",
    title: "用户痛点",
    detail: "脚本、录屏、剪辑分散在多个工具，制作一条功能视频需要数天。",
    evidence: "截图 01 · 首页主张",
    confirmed: true,
    tone: "coral",
  },
  {
    id: "claim-value",
    title: "核心价值",
    detail: "AI 理解产品素材，生成可以直接修改的脚本、镜头、旁白和字幕。",
    evidence: "截图 01 · 功能模块",
    confirmed: true,
    tone: "green",
  },
  {
    id: "claim-output",
    title: "交付结果",
    detail: "同一个产品故事可以快速输出横版和竖版视频。",
    evidence: "截图 01 · 输出规格",
    confirmed: true,
    tone: "cyan",
  },
];

export const initialScenes: StoryScene[] = [
  {
    id: "scene-01",
    purpose: "开场",
    narration: "一个产品网址、几张截图，或者一段录屏，就能变成一支讲得清楚的产品视频。",
    visual: "素材入口依次出现，光标停在截图上传区域。",
    duration: "4.6 秒",
  },
  {
    id: "scene-02",
    purpose: "用户问题",
    narration: "产品已经上线，介绍它却还要写脚本、录屏、剪辑好几天。",
    visual: "分散的任务收拢成一条生成流程。",
    duration: "4.1 秒",
  },
  {
    id: "scene-03",
    purpose: "产品价值",
    narration: "神机妙述先理解用户痛点、产品价值和页面证据，再规划每一个镜头。",
    visual: "三条分析结果逐项确认，并显示对应素材证据。",
    duration: "5.2 秒",
  },
  {
    id: "scene-04",
    purpose: "工作流程",
    narration: "脚本、画面、旁白和字幕自动生成。修改文字，就是修改视频。",
    visual: "编辑脚本时，右侧视频预览同步更新。",
    duration: "4.8 秒",
  },
  {
    id: "scene-05",
    purpose: "多种格式",
    narration: "同一个故事，一次生成横版讲解和竖版短视频。",
    visual: "十六比九和九比十六两个输出同时完成。",
    duration: "3.8 秒",
  },
  {
    id: "scene-06",
    purpose: "行动指引",
    narration: "神机妙述，自动讲清你的产品。",
    visual: "品牌收尾与开始制作按钮。",
    duration: "3.1 秒",
  },
];
