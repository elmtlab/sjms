"""神机妙述 render + TTS service v0.

Run:  uvicorn app:app --host 0.0.0.0 --port 8787
Jobs are persisted under ./jobs/<id>/ (job.json + outputs).
"""
import hashlib
import json
import os
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import engine
import tts as tts_mod
from schema import RenderRequest, SynthRequest

ROOT = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(ROOT, "jobs")
TTS_CACHE = os.path.join(ROOT, "tts-cache")
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(TTS_CACHE, exist_ok=True)

app = FastAPI(title="miaoshu-service", version="0.1.0")
_jobs = {}
_lock = threading.Lock()


def _persist(job):
    with open(os.path.join(JOBS_DIR, job["job_id"], "job.json"), "w") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def _set(job, **kw):
    with _lock:
        job.update(kw)
        _persist(job)


def _synth_cached(provider, voice, text):
    """TTS with content-addressed cache: same text+voice never re-synthesized."""
    key = hashlib.sha1(f"{provider}|{voice}|{text}".encode()).hexdigest()[:20]
    wav = os.path.join(TTS_CACHE, key + ".wav")
    meta = os.path.join(TTS_CACHE, key + ".json")
    if os.path.exists(wav) and os.path.exists(meta):
        with open(meta) as f:
            m = json.load(f)
        return tts_mod.TTSResult(wav, m["duration"], m["words"], m["chars"]), True
    r = tts_mod.get_tts(provider).synth(text, voice, "+0%", wav)
    with open(meta, "w") as f:
        json.dump({"duration": r.duration, "words": r.words, "chars": r.chars}, f,
                  ensure_ascii=False)
    return r, False


def _run_job(job, req: RenderRequest):
    try:
        workdir = os.path.join(JOBS_DIR, job["job_id"])
        scenes = req.storyboard.scenes

        _set(job, status="tts", progress=0.05)
        t0 = time.time()
        vo_results = []
        cache_hits = 0
        for sc in scenes:
            r, hit = _synth_cached(req.tts_provider, req.voice, sc.voiceover)
            cache_hits += hit
            vo_results.append(r)
        tts_wall = time.time() - t0

        # backfill duration_ms into the storyboard (contract: TTS drives timing)
        _, durs, _, total = engine.compute_timeline(scenes, [r.duration for r in vo_results])
        for sc, d in zip(scenes, durs):
            sc.duration_ms = int(d * 1000)
        _set(job, storyboard=json.loads(req.storyboard.model_dump_json()))

        outputs = []
        for k, aspect in enumerate(req.aspects):
            _set(job, status=f"render:{aspect}",
                 progress=0.1 + 0.8 * k / len(req.aspects))
            out = os.path.join(workdir, f"final-{aspect.replace(':', 'x')}.mp4")
            rep = engine.render_video(
                req.storyboard, aspect, vo_results, out, workdir,
                progress_cb=lambda p, k=k: _set(
                    job, progress=0.1 + 0.8 * (k + p) / len(req.aspects)))
            rep["qc"] = engine.qc_check(out, rep["total_s"], aspect)
            rep["bytes"] = os.path.getsize(out)
            rep["path"] = os.path.basename(out)
            outputs.append(rep)

        metering = {
            "tts_chars": sum(r.chars for r in vo_results),
            "tts_cache_hits": cache_hits,
            "tts_wall_s": round(tts_wall, 1),
            "render_wall_s": sum(o["render_wall_s"] for o in outputs),
            "output_seconds": sum(o["total_s"] for o in outputs),
            "output_bytes": sum(o["bytes"] for o in outputs),
        }
        ok = all(o["qc"]["pass"] for o in outputs)
        _set(job, status="complete" if ok else "failed_qc", progress=1.0,
             outputs=outputs, metering=metering, finished_at=time.time())
    except Exception as e:  # noqa: BLE001 — job must record any failure
        _set(job, status="failed", error=f"{type(e).__name__}: {e}",
             finished_at=time.time())


@app.get("/health")
def health():
    return {"ok": True, "service": "miaoshu-service", "version": "0.1.0"}


@app.post("/v1/renders", status_code=202)
def create_render(req: RenderRequest):
    job_id = uuid.uuid4().hex[:12]
    os.makedirs(os.path.join(JOBS_DIR, job_id), exist_ok=True)
    job = {"job_id": job_id, "status": "queued", "progress": 0.0,
           "aspects": req.aspects, "voice": req.voice,
           "created_at": time.time()}
    with _lock:
        _jobs[job_id] = job
    _persist(job)
    threading.Thread(target=_run_job, args=(job, req), daemon=True).start()
    return {"job_id": job_id, "status_url": f"/v1/jobs/{job_id}"}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        p = os.path.join(JOBS_DIR, job_id, "job.json")
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        raise HTTPException(404, "job not found")
    return job


@app.get("/v1/jobs/{job_id}/outputs/{aspect_key}")
def get_output(job_id: str, aspect_key: str):
    path = os.path.join(JOBS_DIR, job_id, f"final-{aspect_key}.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "output not found")
    return FileResponse(path, media_type="video/mp4")


@app.post("/v1/tts/synth")
def synth(req: SynthRequest):
    r, cached = _synth_cached(req.provider, req.voice, req.text)
    return {"duration": r.duration, "chars": r.chars, "cached": cached,
            "words": r.words,
            "audio_url": f"/v1/tts/audio/{os.path.basename(r.audio_path)}"}


@app.get("/v1/tts/audio/{name}")
def tts_audio(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400, "bad name")
    path = os.path.join(TTS_CACHE, name)
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="audio/wav")
