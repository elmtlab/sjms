import "server-only";

import { randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const DATA_ROOT = process.env.SJMS_DATA_DIR ?? path.join(process.cwd(), "data");
const PROJECTS_ROOT = path.join(DATA_ROOT, "projects");
const MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024;
const MAX_RECORDING_BYTES = 250 * 1024 * 1024;
const SAFE_ID = /^[a-zA-Z0-9_-]{1,80}$/;

export type SourceKind = "url" | "screenshot" | "recording";

type SourceRecord = {
  sourceId: string;
  kind: SourceKind;
  name: string;
  mimeType: string | null;
  bytes: number | null;
  originalUrl: string | null;
  storageName: string | null;
  createdAt: string;
};

type ProjectRecord = {
  projectId: string;
  name: string;
  audience: string;
  objective: string;
  status: "draft" | "ingesting" | "needs_confirmation" | "planning" | "preview_ready" | "rendering" | "complete" | "failed";
  sources: SourceRecord[];
  understanding: unknown | null;
  createdAt: string;
  updatedAt: string;
};

export type ProjectDTO = Omit<ProjectRecord, "sources"> & {
  sources: Array<Omit<SourceRecord, "storageName"> & { contentUrl: string | null }>;
};

export class StoreError extends Error {
  constructor(message: string, readonly status = 400) {
    super(message);
  }
}

function assertId(value: string, label: string) {
  if (!SAFE_ID.test(value)) throw new StoreError(`Invalid ${label}`, 400);
}

function projectDir(projectId: string) {
  assertId(projectId, "project id");
  return path.join(PROJECTS_ROOT, projectId);
}

function projectFile(projectId: string) {
  return path.join(projectDir(projectId), "project.json");
}

function toDTO(project: ProjectRecord): ProjectDTO {
  return {
    ...project,
    sources: project.sources.map(({ storageName, ...source }) => ({
      ...source,
      contentUrl: storageName ? `/api/projects/${project.projectId}/sources/${source.sourceId}/content` : null,
    })),
  };
}

async function readProjectRecord(projectId: string) {
  try {
    return JSON.parse(await readFile(projectFile(projectId), "utf8")) as ProjectRecord;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new StoreError("Project not found", 404);
    throw error;
  }
}

async function writeProjectRecord(project: ProjectRecord) {
  const directory = projectDir(project.projectId);
  await mkdir(directory, { recursive: true });
  const target = projectFile(project.projectId);
  const temporary = `${target}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(project, null, 2), { encoding: "utf8", mode: 0o600 });
  await rename(temporary, target);
}

function imageType(buffer: Buffer) {
  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return { mime: "image/png", extension: "png" };
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) return { mime: "image/jpeg", extension: "jpg" };
  if (buffer.subarray(0, 4).toString("ascii") === "RIFF" && buffer.subarray(8, 12).toString("ascii") === "WEBP") return { mime: "image/webp", extension: "webp" };
  return null;
}

function recordingType(buffer: Buffer) {
  if (buffer.subarray(4, 8).toString("ascii") === "ftyp") return { mime: "video/mp4", extension: "mp4" };
  if (buffer.subarray(0, 4).equals(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]))) return { mime: "video/webm", extension: "webm" };
  return null;
}

export async function createProject(input: { name: string; audience: string; objective: string }) {
  const now = new Date().toISOString();
  const project: ProjectRecord = {
    projectId: `prj_${randomUUID().replaceAll("-", "").slice(0, 16)}`,
    name: input.name.trim().slice(0, 120) || "未命名项目",
    audience: input.audience.trim().slice(0, 500),
    objective: input.objective.trim().slice(0, 500),
    status: "draft",
    sources: [],
    understanding: null,
    createdAt: now,
    updatedAt: now,
  };
  await writeProjectRecord(project);
  return toDTO(project);
}

export async function listProjects() {
  await mkdir(PROJECTS_ROOT, { recursive: true });
  const entries = await readdir(PROJECTS_ROOT, { withFileTypes: true });
  const projects = await Promise.all(entries.filter((entry) => entry.isDirectory()).map(async (entry) => {
    try { return toDTO(await readProjectRecord(entry.name)); } catch { return null; }
  }));
  return projects.filter((project): project is ProjectDTO => project !== null).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function getProject(projectId: string) {
  return toDTO(await readProjectRecord(projectId));
}

export async function addUrlSource(projectId: string, value: string) {
  const parsed = new URL(value);
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new StoreError("Only HTTP(S) URLs are supported");
  const project = await readProjectRecord(projectId);
  const now = new Date().toISOString();
  project.sources.push({ sourceId: `src_${randomUUID().replaceAll("-", "").slice(0, 16)}`, kind: "url", name: parsed.hostname, mimeType: null, bytes: null, originalUrl: parsed.toString(), storageName: null, createdAt: now });
  project.status = "ingesting";
  project.updatedAt = now;
  await writeProjectRecord(project);
  return toDTO(project);
}

export async function addFileSource(projectId: string, kind: "screenshot" | "recording", file: File) {
  const maxBytes = kind === "screenshot" ? MAX_SCREENSHOT_BYTES : MAX_RECORDING_BYTES;
  if (file.size < 1 || file.size > maxBytes) throw new StoreError(kind === "screenshot" ? "Screenshot must be smaller than 20 MB" : "Recording must be smaller than 250 MB", 413);

  const buffer = Buffer.from(await file.arrayBuffer());
  const detected = kind === "screenshot" ? imageType(buffer) : recordingType(buffer);
  if (!detected) throw new StoreError(kind === "screenshot" ? "Unsupported screenshot format" : "Unsupported recording format", 415);

  const project = await readProjectRecord(projectId);
  const sourceId = `src_${randomUUID().replaceAll("-", "").slice(0, 16)}`;
  const directory = path.join(projectDir(projectId), "sources");
  const storageName = `${sourceId}.${detected.extension}`;
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, storageName), buffer, { mode: 0o600 });

  const now = new Date().toISOString();
  project.sources.push({ sourceId, kind, name: file.name.slice(0, 180), mimeType: detected.mime, bytes: buffer.length, originalUrl: null, storageName, createdAt: now });
  project.status = "ingesting";
  project.updatedAt = now;
  await writeProjectRecord(project);
  return toDTO(project);
}

export async function getSourceContent(projectId: string, sourceId: string) {
  assertId(sourceId, "source id");
  const project = await readProjectRecord(projectId);
  const source = project.sources.find((item) => item.sourceId === sourceId);
  if (!source?.storageName || !source.mimeType) throw new StoreError("Source content not found", 404);
  const filename = path.join(projectDir(projectId), "sources", source.storageName);
  const details = await stat(filename).catch(() => null);
  if (!details?.isFile()) throw new StoreError("Source content not found", 404);
  return { buffer: await readFile(filename), mimeType: source.mimeType, bytes: details.size };
}

export async function saveUnderstanding(projectId: string, understanding: unknown) {
  const project = await readProjectRecord(projectId);
  project.understanding = understanding;
  project.status = "needs_confirmation";
  project.updatedAt = new Date().toISOString();
  await writeProjectRecord(project);
  return toDTO(project);
}

