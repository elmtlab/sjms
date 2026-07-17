"use client";

import Image from "next/image";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Download,
  FileImage,
  Film,
  FolderOpen,
  Globe2,
  Images,
  LayoutGrid,
  Link2,
  LoaderCircle,
  Menu,
  MoreHorizontal,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ScanSearch,
  Settings,
  Sparkles,
  Upload,
  Video,
  WalletCards,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Claim,
  initialBrief,
  initialClaims,
  initialScenes,
  ProductBrief,
  ProjectSource,
  SourceKind,
  StoryScene,
} from "@/lib/demo";

type StudioStep = "sources" | "brief" | "story" | "outputs";
type AnalyzeState = "idle" | "running" | "ready";

type MediaJob = {
  job_id: string;
  status: string;
  progress: number;
  outputs?: { aspect: "16:9" | "9:16"; qc: { pass: boolean } }[];
};

const steps: { id: StudioStep; label: string }[] = [
  { id: "sources", label: "添加素材" },
  { id: "brief", label: "确认产品" },
  { id: "story", label: "编辑故事" },
  { id: "outputs", label: "生成视频" },
];

const sourceOptions: { id: SourceKind; label: string; icon: typeof Images }[] = [
  { id: "screenshot", label: "截图", icon: Images },
  { id: "url", label: "网址", icon: Link2 },
  { id: "recording", label: "录屏", icon: Film },
];

function buildRenderRequest(scenes: StoryScene[]) {
  const visuals = [
    { template: "hook", params: { line1: "产品做完了，", line2_pre: "介绍还要花", line2_hi: " 三天", line2_post: "？", chips: ["写脚本", "录屏", "配音", "剪辑"] } },
    { template: "options", params: { headline: "网址、截图、录屏，都能开始", input_url: "s-j.ai", button: "生成视频 →", options: [{ icon: "link", title: "产品网址", sub: "读取页面与产品主张" }, { icon: "image", title: "产品截图", sub: "识别界面与功能证据" }, { icon: "video", title: "产品录屏", sub: "提取关键操作片段" }] } },
    { template: "features", params: { headline: "AI 先读懂产品", subhead: "每条主张都关联素材证据", browser_url: "s-j.ai", cards: [{ tag: "用户痛点", text: "制作功能视频耗时数天", evidence: "截图 · 首页主张" }, { tag: "核心价值", text: "素材自动变成产品故事", evidence: "截图 · 工作流程" }, { tag: "交付结果", text: "同一故事输出多个画幅", evidence: "截图 · 输出规格" }], done_chip: "产品理解已确认" } },
    { template: "editor", params: { headline: "改文字，就是改视频", panel_title: "脚本编辑器", lines: ["用户问题", "产品价值", "工作流程", "多种格式"], edit_index: 1, edit_new: "一句话讲清核心价值", sync_chip: "改动实时同步到镜头", preview_title: "镜头预览", preview_before: ["自动生成", "产品视频"], preview_after: ["一句话", "讲清产品"] } },
    { template: "formats", params: { headline: "一个故事，多种成片", items: [{ label: "官网 · 16:9" }, { label: "短视频 · 9:16" }, { label: "社交媒体 · 1:1" }] } },
    { template: "cta", params: { title: "神机妙述", slogan: "自动讲清你的产品", byline: "by 神机AI", url: "s-j.ai" } },
  ] as const;

  return {
    storyboard: {
      schema_version: "v0",
      project_id: "sjms-web-demo",
      brand: { name: "神机妙述", byline: "by 神机AI", url: "s-j.ai" },
      music: true,
      scenes: scenes.map((scene, index) => ({
        id: scene.id,
        voiceover: scene.narration,
        visual: visuals[index] ?? visuals[visuals.length - 1],
      })),
    },
    aspects: ["16:9", "9:16"],
    voice: "zh-CN-XiaoxiaoNeural",
    tts_provider: "edge",
  };
}

function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-lockup" aria-label="神机妙述">
      <span className="brand-mark" aria-hidden="true"><i /><i /></span>
      {!compact && <span className="brand-name">神机妙述 <small>by 神机AI</small></span>}
    </div>
  );
}

function StepRail({ current, onChange }: { current: StudioStep; onChange: (step: StudioStep) => void }) {
  const currentIndex = steps.findIndex((step) => step.id === current);
  return (
    <nav className="step-rail" aria-label="项目流程">
      {steps.map((step, index) => {
        const completed = index < currentIndex;
        return (
          <button
            key={step.id}
            type="button"
            className={`step-item ${step.id === current ? "is-active" : ""} ${completed ? "is-complete" : ""}`}
            onClick={() => onChange(step.id)}
          >
            <span>{completed ? <Check size={14} strokeWidth={3} /> : index + 1}</span>
            <strong>{step.label}</strong>
          </button>
        );
      })}
    </nav>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      {open && <button type="button" className="sidebar-scrim" aria-label="关闭菜单" onClick={onClose} />}
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="sidebar-head">
          <LogoMark />
          <button type="button" className="icon-button sidebar-close" title="收起菜单" onClick={onClose}><PanelLeftClose size={18} /></button>
        </div>
        <button type="button" className="new-project-button"><Plus size={17} strokeWidth={2.4} />新建项目</button>
        <div className="nav-section">
          <span className="nav-label">工作区</span>
          <button type="button" className="nav-row is-active"><FolderOpen size={17} />项目</button>
          <button type="button" className="nav-row"><LayoutGrid size={17} />风格</button>
        </div>
        <div className="project-list">
          <span className="nav-label">最近项目</span>
          <button type="button" className="project-row is-current">
            <span className="project-thumb"><Video size={15} /></span>
            <span><strong>神机妙述官网介绍</strong><small>刚刚编辑</small></span>
          </button>
          <button type="button" className="project-row">
            <span className="project-thumb alt"><Sparkles size={15} /></span>
            <span><strong>智能客服功能发布</strong><small>昨天</small></span>
          </button>
        </div>
        <div className="sidebar-foot">
          <button type="button" className="nav-row"><CircleHelp size={17} />帮助</button>
          <button type="button" className="nav-row"><Settings size={17} />设置</button>
          <div className="account-row">
            <span className="avatar">SJ</span>
            <span><strong>神机AI</strong><small>s-j.ai</small></span>
            <MoreHorizontal size={17} />
          </div>
        </div>
      </aside>
    </>
  );
}

function SourcePanel({ mode, setMode, sources, setSources, onAnalyze, analyzeState, progress }: {
  mode: SourceKind;
  setMode: (mode: SourceKind) => void;
  sources: ProjectSource[];
  setSources: React.Dispatch<React.SetStateAction<ProjectSource[]>>;
  onAnalyze: () => void;
  analyzeState: AnalyzeState;
  progress: number;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("https://s-j.ai");
  const [dragging, setDragging] = useState(false);

  const addFiles = (files: FileList | File[]) => {
    const next = Array.from(files).map((file, index) => ({
      id: `${Date.now()}-${index}`,
      kind: mode,
      name: file.name,
      meta: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
    }));
    setSources((current) => [...current, ...next]);
  };

  const addDemo = () => {
    setMode("screenshot");
    setSources((current) => [
      ...current.filter((source) => source.id !== "demo-source"),
      { id: "demo-source", kind: "screenshot", name: "神机妙述-首页.png", meta: "1920 × 1080 · 演示素材", preview: "/demo-product-frame.jpg" },
    ]);
  };

  const addUrl = () => {
    if (!url.trim()) return;
    setSources((current) => [
      ...current.filter((source) => source.kind !== "url"),
      { id: `url-${Date.now()}`, kind: "url", name: url.trim(), meta: "等待抓取" },
    ]);
  };

  const accept = mode === "screenshot" ? "image/png,image/jpeg,image/webp" : "video/mp4,video/quicktime,video/webm";

  return (
    <section className="workspace-section source-workspace">
      <div className="section-heading">
        <div><span className="eyebrow">新项目</span><h1>添加产品素材</h1></div>
        <button type="button" className="text-button" onClick={addDemo}><Sparkles size={16} />使用演示素材</button>
      </div>
      <div className="source-tabs" role="tablist" aria-label="素材类型">
        {sourceOptions.map((option) => {
          const Icon = option.icon;
          return (
            <button key={option.id} type="button" role="tab" aria-selected={mode === option.id} className={mode === option.id ? "is-active" : ""} onClick={() => setMode(option.id)}>
              <Icon size={18} />{option.label}
            </button>
          );
        })}
      </div>
      {mode === "url" ? (
        <div className="url-entry">
          <Globe2 size={21} />
          <input value={url} onChange={(event) => setUrl(event.target.value)} aria-label="产品网址" placeholder="https://s-j.ai" />
          <button type="button" className="secondary-button" onClick={addUrl}>添加</button>
        </div>
      ) : (
        <button
          type="button"
          className={`drop-zone ${dragging ? "is-dragging" : ""}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(event: DragEvent<HTMLButtonElement>) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event: DragEvent<HTMLButtonElement>) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}
        >
          <span className="upload-icon"><Upload size={24} /></span>
          <strong>{mode === "screenshot" ? "上传产品截图" : "上传产品录屏"}</strong>
          <small>{mode === "screenshot" ? "PNG、JPG、WebP · 单张不超过 20 MB" : "MP4、MOV、WebM · 不超过 5 分钟"}</small>
          <input ref={fileInput} type="file" multiple accept={accept} tabIndex={-1} onChange={(event: ChangeEvent<HTMLInputElement>) => event.target.files && addFiles(event.target.files)} />
        </button>
      )}
      <div className="source-list-band">
        <div className="band-heading"><strong>已添加素材</strong><span>{sources.length} 项</span></div>
        {sources.length === 0 ? (
          <div className="empty-row"><FileImage size={19} />尚未添加素材</div>
        ) : (
          <div className="source-list">
            {sources.map((source) => (
              <div className="source-file" key={source.id}>
                <span className="file-preview">
                  {source.preview ? <Image src={source.preview} alt="" fill sizes="56px" unoptimized /> : source.kind === "url" ? <Globe2 size={20} /> : <Film size={20} />}
                </span>
                <span className="file-copy"><strong>{source.name}</strong><small>{source.meta}</small></span>
                <span className="ready-badge"><Check size={13} /> 已就绪</span>
                <button type="button" className="icon-button" title="移除素材" onClick={() => setSources((current) => current.filter((item) => item.id !== source.id))}><X size={17} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
      {analyzeState === "running" && (
        <div className="analysis-progress" aria-live="polite">
          <span><LoaderCircle size={18} className="spin" />正在理解产品素材</span><strong>{progress}%</strong>
          <i><b style={{ width: `${progress}%` }} /></i>
        </div>
      )}
      <div className="action-row end">
        <button type="button" className="primary-button" disabled={sources.length === 0 || analyzeState === "running"} onClick={onAnalyze}>
          {analyzeState === "running" ? <LoaderCircle size={18} className="spin" /> : <ScanSearch size={18} />}分析产品<ArrowRight size={17} />
        </button>
      </div>
    </section>
  );
}

function BriefPanel({ brief, setBrief, claims, setClaims, onBack, onNext }: {
  brief: ProductBrief;
  setBrief: React.Dispatch<React.SetStateAction<ProductBrief>>;
  claims: Claim[];
  setClaims: React.Dispatch<React.SetStateAction<Claim[]>>;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <section className="workspace-section">
      <div className="section-heading">
        <div><span className="eyebrow">AI 分析完成</span><h1>确认产品理解</h1></div>
        <span className="confidence"><Sparkles size={15} />可信度 94%</span>
      </div>
      <div className="brief-grid">
        <div className="field-group"><label htmlFor="audience">目标用户</label><input id="audience" value={brief.audience} onChange={(event) => setBrief((current) => ({ ...current, audience: event.target.value }))} /></div>
        <div className="field-group"><label htmlFor="objective">视频目标</label><input id="objective" value={brief.objective} onChange={(event) => setBrief((current) => ({ ...current, objective: event.target.value }))} /></div>
        <div className="field-group span-two"><label htmlFor="problem">用户问题</label><textarea id="problem" value={brief.problem} onChange={(event) => setBrief((current) => ({ ...current, problem: event.target.value }))} /></div>
        <div className="field-group span-two"><label htmlFor="value">核心价值</label><textarea id="value" value={brief.value} onChange={(event) => setBrief((current) => ({ ...current, value: event.target.value }))} /></div>
      </div>
      <div className="claim-section">
        <div className="band-heading"><strong>产品主张</strong><span>{claims.filter((claim) => claim.confirmed).length}/{claims.length} 已确认</span></div>
        <div className="claim-list">
          {claims.map((claim) => (
            <div className={`claim-row tone-${claim.tone}`} key={claim.id}>
              <i />
              <span className="claim-copy"><strong>{claim.title}</strong><b>{claim.detail}</b><small>{claim.evidence}</small></span>
              <label className="check-control">
                <input type="checkbox" checked={claim.confirmed} onChange={() => setClaims((current) => current.map((item) => item.id === claim.id ? { ...item, confirmed: !item.confirmed } : item))} />
                <span><Check size={14} /></span>确认
              </label>
            </div>
          ))}
        </div>
      </div>
      <div className="action-row split">
        <button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={17} />返回素材</button>
        <button type="button" className="primary-button" onClick={onNext}><Sparkles size={17} />生成故事板<ArrowRight size={17} /></button>
      </div>
    </section>
  );
}

function StoryPanel({ scenes, setScenes, onBack, onRender }: {
  scenes: StoryScene[];
  setScenes: React.Dispatch<React.SetStateAction<StoryScene[]>>;
  onBack: () => void;
  onRender: () => void;
}) {
  const [activeId, setActiveId] = useState(scenes[0].id);
  const [aspect, setAspect] = useState<"16:9" | "9:16">("16:9");
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const active = scenes.find((scene) => scene.id === activeId) ?? scenes[0];
  const updateActive = (patch: Partial<StoryScene>) => setScenes((current) => current.map((scene) => scene.id === active.id ? { ...scene, ...patch } : scene));

  const toggleVoice = async () => {
    if (playing) {
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
      setPlaying(false);
      return;
    }

    setPlaying(true);
    try {
      const response = await fetch("/api/media/v1/tts/synth", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: active.narration, voice: "zh-CN-XiaoxiaoNeural", rate: "+8%", provider: "edge" }),
      });
      if (!response.ok) throw new Error("tts unavailable");
      const result = await response.json() as { audio_url: string };
      const audio = new Audio(`/api/media${result.audio_url}`);
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      audio.onerror = () => setPlaying(false);
      await audio.play();
    } catch {
      if (!("speechSynthesis" in window)) { setPlaying(false); return; }
      const utterance = new SpeechSynthesisUtterance(active.narration);
      utterance.lang = "zh-CN";
      utterance.rate = 1.08;
      utterance.onend = () => setPlaying(false);
      window.speechSynthesis.speak(utterance);
    }
  };

  useEffect(() => () => {
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
  }, []);

  return (
    <section className="story-workspace">
      <div className="story-topbar">
        <div><span className="eyebrow">故事板 v1</span><h1>编辑产品故事</h1></div>
        <div className="story-tools">
          <label className="select-control"><span>晓晓 · 温暖亲和</span><ChevronDown size={15} /><select aria-label="旁白音色"><option>晓晓 · 温暖亲和</option><option>云希 · 年轻男声</option><option>云扬 · 稳重专业</option></select></label>
          <button type="button" className="secondary-button" onClick={toggleVoice}>{playing ? <Pause size={17} /> : <Play size={17} />}{playing ? "停止" : "试听"}</button>
          <button type="button" className="primary-button" onClick={onRender}><Sparkles size={17} />生成预览</button>
        </div>
      </div>
      <div className="editor-grid">
        <aside className="scene-list-panel">
          <div className="panel-heading"><strong>{scenes.length} 个镜头</strong><button type="button" className="icon-button" title="添加镜头"><Plus size={17} /></button></div>
          <div className="scene-list">
            {scenes.map((scene, index) => (
              <button type="button" key={scene.id} className={scene.id === active.id ? "is-active" : ""} onClick={() => setActiveId(scene.id)}>
                <span>{String(index + 1).padStart(2, "0")}</span><b>{scene.purpose}</b><small>{scene.duration}</small>
              </button>
            ))}
          </div>
          <button type="button" className="back-link" onClick={onBack}><ArrowLeft size={16} />返回产品理解</button>
        </aside>
        <div className="script-panel">
          <div className="panel-heading"><strong>镜头 {String(scenes.indexOf(active) + 1).padStart(2, "0")} · {active.purpose}</strong><span>{active.duration}</span></div>
          <div className="field-group"><label htmlFor="narration">旁白</label><textarea id="narration" className="narration-input" value={active.narration} onChange={(event) => updateActive({ narration: event.target.value })} /><span className="field-meta">{active.narration.length} 字 · 时长由 TTS 回填</span></div>
          <div className="field-group"><label htmlFor="visual">画面计划</label><textarea id="visual" value={active.visual} onChange={(event) => updateActive({ visual: event.target.value })} /></div>
          <div className="evidence-chip"><Check size={14} />已关联 2 条产品证据</div>
        </div>
        <div className="preview-panel">
          <div className="panel-heading">
            <strong>画面预览</strong>
            <div className="aspect-switch" role="group" aria-label="画幅"><button type="button" className={aspect === "16:9" ? "is-active" : ""} onClick={() => setAspect("16:9")}>16:9</button><button type="button" className={aspect === "9:16" ? "is-active" : ""} onClick={() => setAspect("9:16")}>9:16</button></div>
          </div>
          <div className={`video-stage ${aspect === "9:16" ? "is-vertical" : ""}`}>
            <Image src="/demo-product-frame.jpg" alt="产品视频画面预览" fill sizes="(max-width: 900px) 90vw, 520px" priority />
            <div className="stage-shade" />
            <span className="stage-brand">神机妙述 <small>by 神机AI</small></span>
            <strong>{active.purpose}</strong><p>{active.narration}</p>
            <button type="button" className="stage-play" title="播放镜头" onClick={toggleVoice}>{playing ? <Pause size={20} /> : <Play size={20} fill="currentColor" />}</button>
          </div>
          <div className="preview-footer"><Clock3 size={15} />预计总时长 26 秒<span>自动保存</span></div>
        </div>
      </div>
    </section>
  );
}

function OutputsPanel({ progress, setProgress, onBack, jobId }: { progress: number; setProgress: React.Dispatch<React.SetStateAction<number>>; onBack: () => void; jobId: string | null }) {
  const [mediaJob, setMediaJob] = useState<MediaJob | null>(null);
  const complete = mediaJob?.status === "complete" || (!jobId && progress >= 100);
  useEffect(() => {
    if (jobId || complete) return;
    const timer = window.setInterval(() => setProgress((current) => Math.min(100, current + 4)), 160);
    return () => window.clearInterval(timer);
  }, [complete, jobId, setProgress]);

  useEffect(() => {
    if (!jobId || complete) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(`/api/media/v1/jobs/${jobId}`, { cache: "no-store" });
        if (!response.ok) return;
        const result = await response.json() as MediaJob;
        if (cancelled) return;
        setMediaJob(result);
        setProgress(Math.round(result.progress * 100));
      } catch {
        // The next poll may recover while the local worker restarts.
      }
    };
    void poll();
    const timer = window.setInterval(poll, 1000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [complete, jobId, setProgress]);

  return (
    <section className="workspace-section output-workspace">
      <div className="section-heading"><div><span className="eyebrow">输出库</span><h1>{complete ? "预览已生成" : "正在生成预览"}</h1></div><button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={17} />返回编辑</button></div>
      {!complete ? (
        <div className="render-status"><span className="render-orbit"><LoaderCircle size={30} className="spin" /></span><strong>正在渲染两个画幅</strong><small>配音已完成 · 字幕对齐中 · 预计 18 秒</small><i><b style={{ width: `${progress}%` }} /></i><span>{progress}%</span></div>
      ) : (
        <div className="output-grid">
          <article className="output-item">
            <div className="output-frame wide">
              {jobId ? <video controls preload="metadata" src={`/api/media/v1/jobs/${jobId}/outputs/16x9`} /> : <><Image src="/demo-product-frame.jpg" alt="16:9 产品视频预览" fill sizes="640px" /><button type="button" className="stage-play" title="播放横版预览"><Play size={20} fill="currentColor" /></button></>}
            </div>
            <div className="output-copy"><span><strong>官网讲解版</strong><small>16:9 · 1080p · 26 秒</small></span><a className="icon-button" href={jobId ? `/api/media/v1/jobs/${jobId}/outputs/16x9` : "/demo-product-frame.jpg"} download title="下载横版"><Download size={18} /></a></div>
          </article>
          <article className="output-item">
            <div className="output-frame vertical">
              {jobId ? <video controls preload="metadata" src={`/api/media/v1/jobs/${jobId}/outputs/9x16`} /> : <><Image src="/demo-product-frame.jpg" alt="9:16 产品视频预览" fill sizes="300px" /><button type="button" className="stage-play" title="播放竖版预览"><Play size={20} fill="currentColor" /></button></>}
            </div>
            <div className="output-copy"><span><strong>竖版短视频</strong><small>9:16 · 1080p · 26 秒</small></span><a className="icon-button" href={jobId ? `/api/media/v1/jobs/${jobId}/outputs/9x16` : "/demo-product-frame.jpg"} download title="下载竖版"><Download size={18} /></a></div>
          </article>
        </div>
      )}
      <div className="job-log">
        <div className="band-heading"><strong>生成记录</strong><button type="button" className="icon-button" title="刷新记录"><RefreshCw size={16} /></button></div>
        <div className="job-row"><span className="status-dot success" /><span><strong>普通话旁白</strong><small>晓晓 · 412 字</small></span><b>完成</b></div>
        <div className="job-row"><span className={`status-dot ${complete ? "success" : "running"}`} /><span><strong>预览渲染</strong><small>16:9 + 9:16</small></span><b>{complete ? "通过 QC" : `${progress}%`}</b></div>
      </div>
    </section>
  );
}

export default function Studio() {
  const [mobileNav, setMobileNav] = useState(false);
  const [step, setStep] = useState<StudioStep>("sources");
  const [sourceMode, setSourceMode] = useState<SourceKind>("screenshot");
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [analyzeState, setAnalyzeState] = useState<AnalyzeState>("idle");
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [brief, setBrief] = useState(initialBrief);
  const [claims, setClaims] = useState(initialClaims);
  const [scenes, setScenes] = useState(initialScenes);
  const [renderProgress, setRenderProgress] = useState(0);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const activeIndex = useMemo(() => steps.findIndex((item) => item.id === step), [step]);

  const analyze = () => {
    setAnalyzeState("running");
    setAnalysisProgress(8);
    const timer = window.setInterval(() => {
      setAnalysisProgress((current) => {
        const next = Math.min(100, current + Math.ceil(Math.random() * 15));
        if (next >= 100) {
          window.clearInterval(timer);
          window.setTimeout(() => { setAnalyzeState("ready"); setStep("brief"); }, 280);
        }
        return next;
      });
    }, 180);
  };

  const startRender = async () => {
    setRenderProgress(4);
    setRenderJobId(null);
    setStep("outputs");
    try {
      const response = await fetch("/api/media/v1/renders", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(buildRenderRequest(scenes)),
      });
      if (!response.ok) return;
      const result = await response.json() as { job_id: string };
      setRenderJobId(result.job_id);
    } catch {
      // Demo progress remains available when the local media service is offline.
    }
  };

  return (
    <div className="app-shell">
      <Sidebar open={mobileNav} onClose={() => setMobileNav(false)} />
      <div className="app-main">
        <header className="topbar">
          <button type="button" className="icon-button mobile-menu" title="打开菜单" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
          <div className="mobile-brand"><LogoMark /></div>
          <div className="project-title"><span>神机妙述官网介绍</span><small>已保存</small></div>
          <div className="topbar-actions"><button type="button" className="credits-button"><WalletCards size={16} /><strong>126</strong><span>点数</span></button><button type="button" className="avatar-button" title="账户设置">SJ</button></div>
        </header>
        <StepRail current={step} onChange={(next) => { const nextIndex = steps.findIndex((item) => item.id === next); if (nextIndex <= activeIndex || analyzeState === "ready") setStep(next); }} />
        <main className="main-canvas">
          {step === "sources" && <SourcePanel mode={sourceMode} setMode={setSourceMode} sources={sources} setSources={setSources} onAnalyze={analyze} analyzeState={analyzeState} progress={analysisProgress} />}
          {step === "brief" && <BriefPanel brief={brief} setBrief={setBrief} claims={claims} setClaims={setClaims} onBack={() => setStep("sources")} onNext={() => setStep("story")} />}
          {step === "story" && <StoryPanel scenes={scenes} setScenes={setScenes} onBack={() => setStep("brief")} onRender={startRender} />}
          {step === "outputs" && <OutputsPanel progress={renderProgress} setProgress={setRenderProgress} onBack={() => setStep("story")} jobId={renderJobId} />}
        </main>
      </div>
    </div>
  );
}
