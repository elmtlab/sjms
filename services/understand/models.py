"""Pydantic models mirroring contracts/product-understanding.schema.json (v0.1).

Field names are camelCase on the wire to match the canonical contract exactly;
this service speaks the contract, adapters translate for internal use.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceId: str
    artifactId: Optional[str] = None
    locator: str
    excerpt: Optional[str] = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimId: str
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    evidence: List[Evidence] = Field(default_factory=list)


class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    featureId: str
    name: str
    benefit: str
    claimIds: List[str] = Field(default_factory=list)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceId: str
    kind: Literal["url", "screenshot", "recording"]
    originalUrl: Optional[str] = None
    artifactIds: List[str] = Field(default_factory=list)
    status: Literal["ready", "failed", "excluded"] = "ready"


class BrandHints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logoArtifactId: Optional[str] = None
    colors: List[str] = Field(default_factory=list, max_length=5)


class ProductUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["0.1"] = "0.1"
    projectId: str
    revision: int = 1
    sources: List[Source] = Field(min_length=1)
    productName: Optional[str] = None
    audience: str
    objective: Literal["feature_education", "launch", "conversion", "onboarding"]
    problem: Optional[str] = None
    valueProposition: Optional[str] = None
    claims: List[Claim] = Field(default_factory=list)
    features: List[Feature] = Field(default_factory=list)
    # contract: brand must be an object when present (never null)
    brand: BrandHints = Field(default_factory=BrandHints)


class Hints(BaseModel):
    """Optional operator-provided context passed to the VLM."""
    productName: Optional[str] = None
    audience: str = "潜在客户"
    objective: Literal["feature_education", "launch", "conversion", "onboarding"] = "feature_education"


class UnderstandRequest(BaseModel):
    projectId: str
    # v0 single-machine deployment: artifacts are local file paths written by
    # the web upload layer. Raw URLs are NOT accepted; ingestion resolves those.
    sources: List[Source] = Field(min_length=1)
    artifactPaths: dict = Field(default_factory=dict)  # artifactId -> local path
    hints: Hints = Field(default_factory=Hints)
    provider: Literal["mock", "glm", "qwen", "claude", "openai"] = "mock"


class BrandOverride(BaseModel):
    name: str
    byline: str = ""
    url: str = ""


class PlanRequest(BaseModel):
    understanding: ProductUnderstanding
    brand: Optional[BrandOverride] = None
    voice: str = "zh-CN-XiaoxiaoNeural"
    aspects: List[Literal["16:9", "9:16"]] = Field(default_factory=lambda: ["16:9"])
