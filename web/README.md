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

