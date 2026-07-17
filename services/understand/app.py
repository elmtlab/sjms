"""Understanding service v0.

Run:  uvicorn app:app --host 0.0.0.0 --port 8788

POST /v1/understand  — screenshots (resolved local artifacts) -> ProductUnderstanding
POST /v1/plan        — ProductUnderstanding (+brand snapshot) -> render request JSON
POST /v1/pipeline    — convenience: understand + plan in one call
"""
import time

from fastapi import FastAPI, HTTPException

import planner
import vlm
from models import PlanRequest, UnderstandRequest

app = FastAPI(title="understand-service", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True, "service": "understand-service", "version": "0.1.0"}


def _analyze(req: UnderstandRequest):
    provider = vlm.get_vlm(req.provider)
    t0 = time.time()
    try:
        u = provider.analyze(req)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e)) from e
    meta = {"provider": req.provider, "model": provider.model,
            "prompt_version": vlm.PROMPT_VERSION,
            "wall_s": round(time.time() - t0, 1)}
    return u, meta


@app.post("/v1/understand")
def understand(req: UnderstandRequest):
    u, meta = _analyze(req)
    return {"understanding": u.model_dump(), "meta": meta}


@app.post("/v1/plan")
def plan(req: PlanRequest):
    return planner.plan(req)


@app.post("/v1/pipeline")
def pipeline(req: UnderstandRequest, voice: str = "zh-CN-XiaoxiaoNeural"):
    u, meta = _analyze(req)
    render_req = planner.plan(PlanRequest(understanding=u, voice=voice,
                                          aspects=["16:9", "9:16"]))
    return {"understanding": u.model_dump(), "meta": meta,
            "render_request": render_req}
