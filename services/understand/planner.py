"""Rule-based storyboard planner v0: ProductUnderstanding -> renderable storyboard.

Deterministic and testable. Output matches services/media schema (snake_case,
brand snapshot embedded). An LLM planner can later replace this behind the
same plan() signature.

Scene plan by objective:
- hook      always (problem -> pain statement)
- options   only for objective=onboarding (top-3 features as entry points)
- features  always (top-3 claims by confidence, evidence shown)
- formats   for launch/conversion (multi-channel close)
- cta       always (productName + valueProposition)
"""
import re

from models import PlanRequest, ProductUnderstanding

MAX_VO = 40  # chars per voiceover line — keeps TTS lines in a 3-7s band


def _clip(s, n):
    s = (s or "").strip()
    return s[:n]


def _hook_params(u: ProductUnderstanding):
    problem = u.problem or "重复工作占用太多时间"
    parts = re.split(r"[，,]", problem, maxsplit=1)
    line1 = _clip(parts[0], 12) + "，"
    rest = _clip(parts[1] if len(parts) > 1 else "还要再花几天？", 14)
    if not rest.endswith(("？", "?")):
        rest += "？"
    # highlight a number+unit if present, else the tail
    m = re.search(r"(\d+\s*[天小时分钟个月周]+)", rest)
    if m:
        pre, hi = rest[:m.start()], m.group(1)
        post = rest[m.end():] or "？"
    else:
        pre, hi, post = rest[:-3] if len(rest) > 3 else "", rest[-3:-1] or rest, "？"
        if rest[-1] in "？?":
            post = "？"
    # hook chips represent pain points (rendered with ✕); feature names would
    # read as crossed-out capabilities, so omit until the VLM extracts pains.
    return {"line1": line1, "line2_pre": pre, "line2_hi": " " + hi.strip(),
            "line2_post": post, "chips": []}


_ICONS = ["image", "doc", "video", "check"]


def _options_params(u: ProductUnderstanding):
    opts = [{"icon": _ICONS[i % 4], "title": _clip(f.name, 10),
             "sub": _clip(f.benefit, 14)} for i, f in enumerate(u.features[:3])]
    return {"headline": _clip((u.valueProposition or "轻松开始"), 16),
            "options": opts}


def _features_params(u: ProductUnderstanding):
    ranked = sorted([c for c in u.claims if c.status != "rejected"],
                    key=lambda c: -c.confidence)[:3]
    cards = []
    for i, c in enumerate(ranked):
        ev = c.evidence[0] if c.evidence else None
        cards.append({"tag": f"卖点 {i+1}", "text": _clip(c.text, 20),
                      "evidence": f"证据 · {ev.excerpt or ev.locator}" if ev else "证据 · 用户确认"})
    url = ""
    for s in u.sources:
        if s.originalUrl:
            url = re.sub(r"^https?://", "", s.originalUrl)
            break
    return {"headline": "真实卖点，有据可查",
            "subhead": "每条主张都来自你的产品素材",
            "browser_url": url or (u.productName or ""),
            "cards": cards}


def _formats_params(u: ProductUnderstanding):
    return {"headline": "一次生成，处处可发",
            "items": [{"label": "16:9 · 官网 / 发布会"},
                      {"label": "9:16 · 抖音 / 视频号"},
                      {"label": "1:1 · 朋友圈 / 广告"}]}


def _vo(text):
    return _clip(text, MAX_VO)


def plan(req: PlanRequest) -> dict:
    u = req.understanding
    name = (req.brand.name if req.brand else None) or u.productName or "你的产品"
    slogan = _clip(u.valueProposition or "让产品自己说话", 14)
    scenes = []

    scenes.append({
        "id": "scene_hook",
        "voiceover": _vo(u.problem or f"{name}的用户，还在为重复工作花时间？"),
        "visual": {"template": "hook", "params": _hook_params(u)}})

    if u.objective == "onboarding" and u.features:
        p = _options_params(u)
        titles = "、".join(o["title"] for o in p["options"])
        scenes.append({
            "id": "scene_options",
            "voiceover": _vo(f"{titles}，都能直接上手。"),
            "visual": {"template": "options", "params": p}})

    fp = _features_params(u)
    top = fp["cards"][0]["text"] if fp["cards"] else ""
    scenes.append({
        "id": "scene_features",
        "voiceover": _vo(f"{top}，每一条卖点都有据可查。" if top
                         else "核心能力一目了然，句句有据。"),
        "visual": {"template": "features", "params": fp}})

    if u.objective in ("launch", "conversion"):
        scenes.append({
            "id": "scene_formats",
            "voiceover": _vo("横版、竖版、方形，一次生成，直接发布。"),
            "visual": {"template": "formats", "params": _formats_params(u)}})

    scenes.append({
        "id": "scene_cta",
        "voiceover": _vo(f"{name}，{slogan}。"),
        "visual": {"template": "cta", "params": {
            "title": name, "slogan": slogan,
            "byline": (req.brand.byline if req.brand else "") or "",
            "url": (req.brand.url if req.brand else "") or ""}}})

    storyboard = {
        "schema_version": "v0",
        "project_id": u.projectId,
        "brand": {"name": name,
                  "byline": (req.brand.byline if req.brand else "") or "",
                  "url": (req.brand.url if req.brand else "") or ""},
        "music": True,
        "scenes": scenes,
    }
    return {"storyboard": storyboard, "aspects": req.aspects,
            "voice": req.voice, "tts_provider": "edge"}
