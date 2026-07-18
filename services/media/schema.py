"""Storyboard schema v0 — the canonical, renderable contract.

Boundaries agreed with the PRD side:
- `duration_ms` is OPTIONAL on input; the pipeline backfills it from actual
  TTS audio duration. Client-supplied values are treated as minimums only.
- The renderer never receives raw URLs/screenshots/recordings. Visual params
  carry template text params and (future) resolved `asset_id` references.
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Aspect = Literal["16:9", "9:16"]

TEMPLATE_NAMES = ("hook", "options", "features", "editor", "formats", "cta")


class Visual(BaseModel):
    template: Literal["hook", "options", "features", "editor", "formats", "cta"]
    # Template-specific text/structure params. Values may reference resolved
    # assets as {"asset_id": "..."} in later versions; raw URLs are rejected
    # at the API layer, not fetched here.
    params: Dict = Field(default_factory=dict)


class Scene(BaseModel):
    id: str
    voiceover: str = Field(min_length=1, max_length=200)
    subtitle: Optional[str] = None       # defaults to voiceover
    visual: Visual
    duration_ms: Optional[int] = None    # backfilled from TTS; input = minimum


class Brand(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    byline: str = ""
    url: str = ""


class Storyboard(BaseModel):
    schema_version: Literal["v0"] = "v0"
    project_id: str = "adhoc"
    brand: Brand
    scenes: List[Scene] = Field(min_length=1, max_length=12)
    music: bool = True


class RenderRequest(BaseModel):
    storyboard: Storyboard
    aspects: List[Aspect] = Field(default_factory=lambda: ["16:9"])
    voice: str = "zh-CN-XiaoxiaoNeural"
    tts_provider: Literal["edge", "say"] = "edge"


class SynthRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    provider: Literal["edge", "say"] = "edge"
