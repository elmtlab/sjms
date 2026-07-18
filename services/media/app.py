"""神机妙述 render + TTS service.

Run:  uvicorn app:app --host 0.0.0.0 --port 8787

The API process never renders: each job runs in an isolated worker process
(`worker.py`), with `job.json` on disk as the single source of truth. This
keeps the API responsive (no GIL contention) and immune to macOS demoting a
backgrounded service to efficiency cores; it is also the contract's
API/worker boundary.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from schema import RenderRequest, SynthRequest
from worker import synth_cached, TTS_CACHE

ROOT = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(ROOT, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

app = FastAPI(title="miaoshu-service", version="0.2.0")
_procs = {}  # job_id -> Popen (liveness only; state lives in job.json)


def _job_path(job_id):
    return os.path.join(JOBS_DIR, job_id, "job.json")


def _read_job(job_id):
    p = _job_path(job_id)
    if not os.path.exists(p):
        raise HTTPException(404, "job not found")
    with open(p) as f:
        return json.load(f)


def _spawn_worker(job_dir):
    cmd = [sys.executable, os.path.join(ROOT, "worker.py"), job_dir]
    # keep the worker on performance cores even if the service is backgrounded
    if sys.platform == "darwin" and shutil.which("taskpolicy"):
        cmd = ["taskpolicy", "-c", "utility"] + cmd
    return subprocess.Popen(cmd, cwd=ROOT, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@app.get("/health")
def health():
    return {"ok": True, "service": "miaoshu-service", "version": "0.2.0"}


@app.post("/v1/renders", status_code=202)
def create_render(req: RenderRequest):
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    with open(os.path.join(job_dir, "request.json"), "w") as f:
        f.write(req.model_dump_json())
    job = {"job_id": job_id, "status": "queued", "progress": 0.0,
           "aspects": req.aspects, "voice": req.voice,
           "created_at": time.time()}
    with open(_job_path(job_id), "w") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    _procs[job_id] = _spawn_worker(job_dir)
    return {"job_id": job_id, "status_url": f"/v1/jobs/{job_id}"}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    job = _read_job(job_id)
    proc = _procs.get(job_id)
    if (job["status"] not in ("complete", "failed", "failed_qc", "cancelled")
            and proc is not None and proc.poll() is not None
            and proc.returncode != 0):
        job["status"] = "failed"
        job["error"] = f"worker exited with code {proc.returncode}"
    return job


@app.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = _read_job(job_id)
    proc = _procs.get(job_id)
    if job["status"] in ("complete", "failed", "failed_qc", "cancelled"):
        return job
    if proc is not None and proc.poll() is None:
        proc.terminate()
    job["status"] = "cancelled"
    job["finished_at"] = time.time()
    with open(_job_path(job_id), "w") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return job


@app.get("/v1/jobs/{job_id}/outputs/{aspect_key}")
def get_output(job_id: str, aspect_key: str):
    if "/" in aspect_key or ".." in aspect_key:
        raise HTTPException(400, "bad aspect")
    path = os.path.join(JOBS_DIR, job_id, f"final-{aspect_key}.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "output not found")
    return FileResponse(path, media_type="video/mp4")


@app.post("/v1/tts/synth")
def synth(req: SynthRequest):
    r, cached = synth_cached(req.provider, req.voice, req.text)
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
