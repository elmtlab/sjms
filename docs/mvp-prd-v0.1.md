# 神机妙述 MVP PRD v0.1

Status: Draft for implementation  
Date: 2026-07-17  
Company: 神机AI  
Website: https://s-j.ai  
Working product name: 神机妙述 (replaceable; not a technical identifier)

## 1. Decisions Already Made

- Audience: domestic Chinese users first.
- Surface: responsive website only; no native app in MVP.
- Deployment: application services run on one home server with Docker Compose.
- Speed: ship a narrow end-to-end workflow before expanding editing features.
- Inputs: URL, screenshots, and screen recordings are equally valid starting points.
- Editing model: script-first. Users do not edit a professional timeline.
- Canonical data: product understanding and storyboard JSON, not rendered timelines.
- Output: one storyboard can render 16:9, 9:16, and later 1:1 variants.
- Timing: synthesized narration determines scene duration and subtitle timing.
- Billing: measure raw provider usage internally; expose predictable credits externally.

## 2. Product Promise

> Give 神机妙述 a URL, screenshots, or a screen recording. It identifies the
> product story, lets the user revise it in words, and produces clear product
> videos in multiple formats.

The MVP succeeds when a product maker can produce a publishable 30-60 second
feature video without writing a script from scratch or learning video editing.

## 3. Initial User

Primary user: a founder, product manager, or marketer at a small software team who
has shipped a product or feature but lacks time and video-editing expertise.

Core job:

> When I need to explain a product or feature, help me turn the material I already
> have into a clear video quickly, so users understand why it matters and what to do.

## 4. MVP Workflow

### 4.1 Create a project

The user names the project, selects a goal, describes the target audience, and adds
one or more sources:

- URL: public product or feature page;
- screenshots: PNG, JPEG, or WebP;
- screen recording: MP4, MOV, or WebM.

Sources may be mixed. A URL is never mandatory.

### 4.2 Understand the product

Each source is normalized independently:

- URL -> safe page fetch + DOM text + Playwright screenshots;
- screenshots -> OCR + vision analysis;
- recording -> audio transcription + scene boundaries + representative frames.

All paths produce one versioned `ProductUnderstanding` object containing audience,
problem, value proposition, claims, features, brand hints, and evidence references.

The user must confirm or edit uncertain claims before script generation. Claims
without evidence are visibly labeled and cannot be presented as verified facts.

### 4.3 Edit the story

The planner creates a 4-8 scene storyboard. The default structure is:

1. hook;
2. user problem;
3. product value;
4. proof or workflow;
5. outcome;
6. call to action.

The editor displays scene sentences and their paired visual plans. Selecting a
sentence selects the scene. Editing narration marks voice and render artifacts
stale. Reordering scenes does not require regenerating product understanding.

### 4.4 Preview and render

The user selects voice, speaking rate, style pack, and output aspect ratios.

1. TTS produces audio, duration, and word timestamps per scene.
2. The storyboard is enriched with exact timing.
3. A low-resolution preview is rendered first.
4. After approval, final 1080p variants render asynchronously.
5. Quality checks validate duration, dimensions, video/audio streams, and sampled
   blank frames before a result becomes downloadable.

The user can leave the page. Job status is delivered with server-sent events and
is also visible after returning.

## 5. Web Information Architecture

```text
/projects                 project list + create
/projects/:id/sources     URL / screenshot / recording input
/projects/:id/brief       extracted understanding + evidence confirmation
/projects/:id/story       script-first scene editor
/projects/:id/outputs     previews, final renders, download, duplicate aspect
/settings/voices          voice samples and defaults
/settings/credits         balance and usage ledger
```

The first release has no freeform canvas and no timeline. Advanced visual controls
are limited to style pack, brand color, logo, voice, rate, and aspect ratio.

## 6. MVP Requirements

### Must have

- mixed source upload and resumable project state;
- evidence-linked product understanding;
- editable 4-8 scene storyboard;
- pluggable TTS with exact audio duration and word timestamps;
- 16:9 and 9:16 preview/final rendering;
- one built-in style pack and basic brand overrides;
- asynchronous jobs with retry, cancel, and error messages;
- credit quote before rendering and atomic credit settlement;
- local operator page for failed jobs, storage, and provider usage.

### Should have

- project/version history;
- duplicate output into another aspect ratio without replanning;
- SSE progress and completion notification;
- export MP4 plus subtitle file.

### Explicitly out of scope

- professional timeline editing;
- native iOS/Android apps;
- user-uploaded executable templates;
- real-time multi-user editing;
- AI avatars and long-form video;
- fully local AI models in the first release.

## 7. Credits and Cost Accounting

The user asked whether billing can be token-based. Internally, yes. Externally,
raw tokens are too unpredictable because URLs, image sets, and recordings produce
very different usage. Use two layers:

### Internal usage ledger

Every provider call records:

- LLM input/output tokens and model;
- vision images/pages or equivalent units;
- ASR seconds;
- TTS characters/seconds and voice;
- render CPU-seconds and output resolution;
- storage bytes and artifact lifetime.

Store immutable `usage_events`; never derive historical cost from current prices.
Each event stores the provider price snapshot and calculated internal cost.

### External credits

Before an expensive action, return a deterministic quote. Example launch rules:

- analysis: quote based on source type and size;
- 30-second first 1080p render: 10 credits;
- another aspect ratio from the same approved storyboard: 3 credits;
- script-only changes: free until TTS/preview is requested;
- provider or system failure: automatically release or refund reserved credits.

Settlement flow:

```text
quote -> reserve credits -> run job -> settle actual product action -> release excess
                            \-> terminal system failure -> full release
```

Do not expose “LLM tokens” as the product currency. Credits can still be named
“神机点数” in the UI and are backed by the internal usage ledger.

## 8. Technical Architecture

### 8.1 Single-server topology

```text
Public ingress (decision required)
  -> reverse proxy / TLS
     -> web-api (Next.js UI + typed HTTP API)
     -> PostgreSQL (projects, versions, jobs, credit ledger)
     -> ingest-worker (URL browser, OCR/vision, recording analysis)
     -> media-worker (TTS adapter, Remotion renderer, FFmpeg QC)
     -> local artifact volume (storage adapter; S3-compatible later)
```

Use a Postgres-backed job queue initially to avoid operating Redis. Run browser and
media work in separate containers with CPU/memory limits. Large files never pass
through React server actions; stream them through explicit upload endpoints to the
artifact volume.

The application can run at home, but AI functions are not fully local: Edge/Azure
TTS and model APIs remain external network dependencies until local models replace
them.

### 8.2 Public access decision

“All application compute at home” is feasible. “No external public ingress of any
kind” is only feasible for LAN/private testing unless the home connection has a
reachable public IPv4/IPv6 address and permits inbound ports.

Choose one launch mode after checking the ISP/router:

| Mode | External dependency | Use |
|---|---|---|
| LAN/private alpha | none | team-only validation |
| Public IP/IPv6 + DDNS + port forwarding | DNS only | cheapest public pilot if ISP permits |
| Managed tunnel | tunnel provider | fastest NAT traversal, but adds provider dependency |
| Small public VPS + frp | public VPS | controllable ingress; app/media stay at home |

For stable domestic public launch, confirm domain, ISP port policy, filing, and
security requirements with the chosen access provider before promising a date.
The architecture must keep ingress replaceable so this decision does not affect
the application containers.

### 8.3 Security boundaries

- URL fetcher blocks private, loopback, link-local, metadata, and DNS-rebinding
  targets to prevent SSRF.
- Browser execution uses an isolated non-root container with no host mounts.
- Validate MIME type from content, not only filename; enforce per-file and project
  size limits.
- Use opaque artifact IDs. Never accept arbitrary filesystem paths in API payloads.
- Uploaded recordings and generated outputs are private by default.
- Secrets live outside Compose files and never reach browser/render templates.
- Database and artifact volumes are backed up before public beta.

## 9. Canonical Contracts

The schemas in this folder are normative for v0:

- `product-understanding.schema.json` - normalized understanding and evidence;
- `storyboard.schema.json` - editable source of truth for narration and visuals;
- `openapi.yaml` - initial HTTP API and async job contract.

Contract rules:

- IDs are opaque strings and stable within a project.
- All mutable aggregates have integer revisions.
- A render references `storyboardId + revision`; it never consumes an unversioned
  “latest” storyboard.
- Render visuals reference artifact IDs, never original URLs or filesystem paths.
- Each storyboard stores a `brand` snapshot (`name`, `byline`, `url`) so a render
  remains reproducible if project-level brand settings later change.
- `durationMs` may be null while drafting, but must be filled from TTS output before
  rendering.
- Worker commands are idempotent using `project + revision + operation + options`.

## 10. Delivery Plan

### Phase 1: contracts and callable media services

- PRD and v0 schemas;
- TTS adapter and one neural Mandarin implementation;
- storyboard-to-video render API and automatic QC;
- Compose skeleton and persistent volumes.

Exit: a fixture storyboard sent to the local API returns a validated MP4.

### Phase 2: thin Web MVP

- project/source pages;
- one normalization path at a time: screenshots first, then URL, then recording;
- product brief confirmation and script-first editor;
- preview/final job UI with SSE progress;
- credit quote/reserve/settle ledger.

Exit: five assisted users complete source-to-published-video without shell access.

### Phase 3: public pilot hardening

- chosen public ingress and TLS;
- authentication, backups, quotas, abuse limits, and operator dashboard;
- provider fallbacks and storage cleanup;
- 10-user assisted pilot.

## 11. Acceptance Metrics

- median time from source submission to editable first story under 3 minutes;
- first low-resolution preview under 90 seconds after story approval;
- at least 70% of assisted users publish/share the output using script-level edits;
- fewer than 10% of confirmed product claims require correction after extraction;
- zero successful charges for terminal system failures;
- at least 95% of final renders pass QC on the first worker attempt.

## 12. Open Decisions

Only these decisions block implementation after the v0 services exist:

1. Is the first alpha LAN/private, or must it be reachable from the public Internet?
2. Which source path launches first? Recommendation: screenshots, because it avoids
   URL security/network variability and recording/ASR complexity.
3. Is “神机妙述” the launch name or only a working name?
4. Which payment provider is used after credits are proven with manual grants?

## References

- Next.js self-hosting: https://nextjs.org/docs/app/guides/self-hosting
- Docker Compose production guidance: https://docs.docker.com/compose/how-tos/production/
- Cloudflare Tunnel outbound connection model: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/
- frp reverse proxy: https://github.com/fatedier/frp
