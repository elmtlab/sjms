"""VLM adapter layer: screenshots -> ProductUnderstanding.

Contract: analyze(req: UnderstandRequest) -> ProductUnderstanding

Providers:
- mock  — deterministic fixture, no network/key; keeps the pipeline and tests
          runnable before credentials exist.
- glm   — Zhipu GLM-4V (open.bigmodel.cn), env ZHIPU_API_KEY.
- qwen  — Alibaba DashScope Qwen-VL (OpenAI-compatible), env DASHSCOPE_API_KEY.

Every provider records model + prompt version alongside the result at the
caller (app.py) for cost/provenance tracking.
"""
import base64
import json
import os
import re

import requests

from models import (Claim, Evidence, Feature, Hints, ProductUnderstanding,
                    UnderstandRequest)

PROMPT_VERSION = "extract-v1"

_EXTRACT_PROMPT = """你是产品分析师。请仔细阅读这些产品截图，输出一个 JSON 对象（只输出 JSON，不要任何其它文字），字段如下：

{
  "productName": "产品名称（截图里找不到就用 null）",
  "problem": "该产品要解决的用户痛点，一句话，25 字以内",
  "valueProposition": "产品的核心价值主张，一句话，20 字以内",
  "claims": [
    {"text": "从截图能看到证据的产品主张，20 字以内",
     "confidence": 0.9,
     "screenshot": 1,
     "excerpt": "截图中支持该主张的原文或界面元素描述"}
  ],
  "features": [
    {"name": "功能名，8 字以内", "benefit": "带来的好处，15 字以内", "claim": 0}
  ]
}

规则：
- claims 最多 5 条，只写截图里确实有依据的，不要编造；confidence 是你对证据强度的判断。
- screenshot 是证据所在截图的序号（从 1 开始）。claim 是 features 引用的 claims 下标（从 0 开始）。
- features 最多 4 条。
- 目标受众：{audience}。视频目标：{objective}。请用受众听得懂的语言。"""


def _mk_understanding(req: UnderstandRequest, raw: dict) -> ProductUnderstanding:
    """Normalize a provider's raw extraction dict into the contract model."""
    src_by_idx = [s for s in req.sources if s.status == "ready"]
    claims = []
    for i, c in enumerate(raw.get("claims", [])[:5]):
        sid = 0
        try:
            sid = max(0, min(int(c.get("screenshot", 1)) - 1, len(src_by_idx) - 1))
        except (TypeError, ValueError):
            pass
        src = src_by_idx[sid]
        art = src.artifactIds[0] if src.artifactIds else None
        claims.append(Claim(
            claimId=f"clm_{i+1}",
            text=str(c.get("text", ""))[:40] or "（空）",
            confidence=float(c.get("confidence", 0.5)),
            status="proposed",
            evidence=[Evidence(sourceId=src.sourceId, artifactId=art,
                               locator=f"screenshot:{sid+1}",
                               excerpt=(c.get("excerpt") or None))]))
    features = []
    for i, f in enumerate(raw.get("features", [])[:4]):
        cid = []
        try:
            k = int(f.get("claim", -1))
            if 0 <= k < len(claims):
                cid = [claims[k].claimId]
        except (TypeError, ValueError):
            pass
        features.append(Feature(featureId=f"ft_{i+1}",
                                name=str(f.get("name", ""))[:16],
                                benefit=str(f.get("benefit", ""))[:30],
                                claimIds=cid))
    return ProductUnderstanding(
        projectId=req.projectId,
        sources=req.sources,
        productName=raw.get("productName") or req.hints.productName,
        audience=req.hints.audience,
        objective=req.hints.objective,
        problem=raw.get("problem"),
        valueProposition=raw.get("valueProposition"),
        claims=claims,
        features=features)


def _parse_json_block(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    return json.loads(m.group(0))


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _collect_images(req: UnderstandRequest, limit=6):
    paths = []
    for s in req.sources:
        if s.status != "ready":
            continue
        for aid in s.artifactIds:
            p = req.artifactPaths.get(aid)
            if p and os.path.exists(p):
                paths.append(p)
    if not paths:
        raise ValueError("no readable artifacts; check artifactPaths")
    return paths[:limit]


class MockVLM:
    """Deterministic fixture provider — no network, no key."""

    model = "mock-vlm-0"

    def analyze(self, req: UnderstandRequest) -> ProductUnderstanding:
        _collect_images(req)  # still validates artifacts exist
        name = req.hints.productName or "示例产品"
        raw = {
            "productName": name,
            "problem": "重复性工作占用大量人工时间",
            "valueProposition": f"让{req.hints.audience}的日常工作自动完成",
            "claims": [
                {"text": f"{name}自动处理核心流程", "confidence": 0.9,
                 "screenshot": 1, "excerpt": "首页主标题区域"},
                {"text": "数据实时同步，无需手工导入", "confidence": 0.8,
                 "screenshot": 1, "excerpt": "功能区第二屏"},
                {"text": "结果一键导出分享", "confidence": 0.7,
                 "screenshot": 2, "excerpt": "导出按钮与分享面板"},
            ],
            "features": [
                {"name": "自动处理", "benefit": "省去手工操作", "claim": 0},
                {"name": "实时同步", "benefit": "数据永远最新", "claim": 1},
                {"name": "一键分享", "benefit": "结果直达同事", "claim": 2},
            ],
        }
        return _mk_understanding(req, raw)


class GLM4V:
    """Zhipu GLM-4V via open.bigmodel.cn. Env: ZHIPU_API_KEY."""

    def __init__(self, model=None):
        self.model = model or os.environ.get("GLM_MODEL", "glm-4v-flash")

    def analyze(self, req: UnderstandRequest) -> ProductUnderstanding:
        key = os.environ.get("ZHIPU_API_KEY")
        if not key:
            raise RuntimeError("ZHIPU_API_KEY not set")
        content = [{"type": "image_url",
                    "image_url": {"url": _b64(p)}}
                   for p in _collect_images(req)]
        content.append({"type": "text", "text": _EXTRACT_PROMPT.format(
            audience=req.hints.audience, objective=req.hints.objective)})
        r = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": self.model,
                  "messages": [{"role": "user", "content": content}],
                  "temperature": 0.2},
            timeout=120)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return _mk_understanding(req, _parse_json_block(text))


class QwenVL:
    """Alibaba DashScope Qwen-VL, OpenAI-compatible mode. Env: DASHSCOPE_API_KEY."""

    def __init__(self, model=None):
        self.model = model or os.environ.get("QWEN_MODEL", "qwen-vl-plus")

    def analyze(self, req: UnderstandRequest) -> ProductUnderstanding:
        key = os.environ.get("DASHSCOPE_API_KEY")
        if not key:
            raise RuntimeError("DASHSCOPE_API_KEY not set")
        content = [{"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_b64(p)}"}}
                   for p in _collect_images(req)]
        content.append({"type": "text", "text": _EXTRACT_PROMPT.format(
            audience=req.hints.audience, objective=req.hints.objective)})
        r = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": self.model,
                  "messages": [{"role": "user", "content": content}],
                  "temperature": 0.2},
            timeout=120)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return _mk_understanding(req, _parse_json_block(text))


class ClaudeVLM:
    """Anthropic Claude vision. Env: ANTHROPIC_API_KEY."""

    def __init__(self, model=None):
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    def analyze(self, req: UnderstandRequest) -> ProductUnderstanding:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        content = [{"type": "image",
                    "source": {"type": "base64", "media_type": "image/png",
                               "data": _b64(p)}}
                   for p in _collect_images(req)]
        content.append({"type": "text", "text": _EXTRACT_PROMPT.format(
            audience=req.hints.audience, objective=req.hints.objective)})
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": 1500,
                  "messages": [{"role": "user", "content": content}]},
            timeout=120)
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"])
        return _mk_understanding(req, _parse_json_block(text))


class OpenAIVLM:
    """OpenAI vision (GPT-4o family). Env: OPENAI_API_KEY."""

    def __init__(self, model=None):
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")

    def analyze(self, req: UnderstandRequest) -> ProductUnderstanding:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        content = [{"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{_b64(p)}"}}
                   for p in _collect_images(req)]
        content.append({"type": "text", "text": _EXTRACT_PROMPT.format(
            audience=req.hints.audience, objective=req.hints.objective)})
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": self.model,
                  "messages": [{"role": "user", "content": content}],
                  "temperature": 0.2},
            timeout=120)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return _mk_understanding(req, _parse_json_block(text))


_PROVIDERS = {"mock": MockVLM, "glm": GLM4V, "qwen": QwenVL,
              "claude": ClaudeVLM, "openai": OpenAIVLM}


def get_vlm(provider: str):
    return _PROVIDERS[provider]()
