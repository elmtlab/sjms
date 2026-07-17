# Web MVP

Next.js script-first workspace for 神机妙述.

## Run locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

The server-side `/api/media/*` proxy connects to the media service at
`MEDIA_API_URL`. When the service is offline, upload analysis and rendering use a
deterministic demo fallback so the complete product flow remains reviewable.

Projects and uploaded files persist under `SJMS_DATA_DIR` (default `./data`). The
current `VISION_PROVIDER=mock` creates contract-valid ProductUnderstanding data;
Bob's vision worker will replace that adapter without changing the Web flow.
Set `UNDERSTANDING_API_URL=http://127.0.0.1:8788` to call the worker's
`POST /v1/understand` endpoint. Both containers must mount `SJMS_DATA_DIR` at the
same absolute path because the single-server v0 contract passes resolved artifact
paths, never raw uploads.

## Run with Docker

From the repository root:

```bash
docker compose -f compose.web.yaml up --build
```

## Available flow

1. Add screenshots, a URL, or a screen recording.
2. Review extracted product claims and evidence.
3. Edit narration and visual plans scene by scene.
4. Preview neural TTS when the media service is available.
5. Submit 16:9 and 9:16 renders and poll the real media job.

## Checks

```bash
npm run lint
npm run build
```
