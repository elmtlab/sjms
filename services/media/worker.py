"""Render job worker — runs one job in an isolated process.

Usage: python3 worker.py <job_dir>

Reads  <job_dir>/request.json   (RenderRequest JSON)
Writes <job_dir>/job.json       (status/progress/outputs/metering, atomic)

Isolation rationale: rendering is CPU-bound and long-running; in-process
threads contend with the API on the GIL, and on macOS a backgrounded service
process gets demoted to efficiency cores (measured 17s vs 73min for the same
video). A dedicated process is also the contract's API/worker boundary.
"""
import hashlib
import json
import os
import sys
import time

import engine
import tts as tts_mod
from schema import RenderRequest

ROOT = os.path.dirname(os.path.abspath(__file__))
TTS_CACHE = os.path.join(ROOT, "tts-cache")
os.makedirs(TTS_CACHE, exist_ok=True)


def synth_cached(provider, voice, text):
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


class JobState:
    """job.json is the single source of truth; writes are atomic."""

    def __init__(self, job_dir):
        self.path = os.path.join(job_dir, "job.json")
        with open(self.path) as f:
            self.data = json.load(f)

    def set(self, **kw):
        self.data.update(kw)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


def run(job_dir):
    job = JobState(job_dir)
    try:
        with open(os.path.join(job_dir, "request.json")) as f:
            req = RenderRequest(**json.load(f))
        scenes = req.storyboard.scenes

        job.set(status="tts", progress=0.05, pid=os.getpid())
        t0 = time.time()
        vo_results = []
        cache_hits = 0
        for sc in scenes:
            r, hit = synth_cached(req.tts_provider, req.voice, sc.voiceover)
            cache_hits += hit
            vo_results.append(r)
        tts_wall = time.time() - t0

        # backfill duration_ms (contract: TTS drives timing)
        _, durs, _, _ = engine.compute_timeline(scenes, [r.duration for r in vo_results])
        for sc, d in zip(scenes, durs):
            sc.duration_ms = int(d * 1000)
        job.set(storyboard=json.loads(req.storyboard.model_dump_json()))

        outputs = []
        for k, aspect in enumerate(req.aspects):
            job.set(status=f"render:{aspect}",
                    progress=0.1 + 0.8 * k / len(req.aspects))
            out = os.path.join(job_dir, f"final-{aspect.replace(':', 'x')}.mp4")
            rep = engine.render_video(
                req.storyboard, aspect, vo_results, out, job_dir,
                progress_cb=lambda p, k=k: job.set(
                    progress=0.1 + 0.8 * (k + p) / len(req.aspects)))
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
        job.set(status="complete" if ok else "failed_qc", progress=1.0,
                outputs=outputs, metering=metering, finished_at=time.time())
        return 0
    except Exception as e:  # noqa: BLE001 — job must record any failure
        job.set(status="failed", error=f"{type(e).__name__}: {e}",
                finished_at=time.time())
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
