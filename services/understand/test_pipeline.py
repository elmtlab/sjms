"""End-to-end pipeline test with the mock provider (no network, no keys).

fake screenshots -> understand(mock) -> validate against the canonical
JSON Schema -> plan -> validate against the media service schema ->
smoke-render one frame per scene through the real engine.

Run: python3 test_pipeline.py
"""
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def make_fake_screenshots(outdir):
    """Two fake landing-page screenshots (what a user would upload)."""
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i, (title, sub) in enumerate([
            ("云账房 — 小微企业 AI 记账", "拍发票 · 连银行 · 自动对账"),
            ("报表一键生成", "利润表 / 资产负债表 / 一键分享老板")]):
        im = Image.new("RGB", (1280, 800), (246, 248, 252))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 1280, 72], fill=(20, 30, 60))
        d.text((40, 26), "yunzhangfang.com", fill=(255, 255, 255))
        d.text((80, 200), title, fill=(20, 30, 60))
        d.text((80, 260), sub, fill=(90, 100, 130))
        d.rectangle([80, 340, 400, 520], fill=(220, 228, 245))
        p = os.path.join(outdir, f"shot{i+1}.png")
        im.save(p)
        paths.append(p)
    return paths


def main():
    sys.path.insert(0, HERE)
    from models import PlanRequest, Source, UnderstandRequest, BrandOverride, Hints
    import planner
    import vlm

    shots = make_fake_screenshots(os.path.join(HERE, "fixtures"))

    req = UnderstandRequest(
        projectId="prj_test",
        sources=[Source(sourceId="src_1", kind="screenshot",
                        artifactIds=["art_1", "art_2"], status="ready")],
        artifactPaths={"art_1": shots[0], "art_2": shots[1]},
        hints=Hints(productName="云账房", audience="小微企业主",
                    objective="conversion"),
        provider="mock")

    u = vlm.get_vlm("mock").analyze(req)
    print("understanding ok:", u.productName, len(u.claims), "claims",
          len(u.features), "features")

    # 1) validate against the canonical contract schema
    import jsonschema
    schema = json.load(open(os.path.join(ROOT, "contracts",
                                         "product-understanding.schema.json")))
    jsonschema.validate(json.loads(u.model_dump_json()), schema)
    print("contract schema validation: PASS")

    # 2) plan and validate against the media service request schema
    rr = planner.plan(PlanRequest(
        understanding=u,
        brand=BrandOverride(name="云账房", byline="小微企业记账",
                            url="yunzhangfang.com"),
        aspects=["16:9"]))
    sys.path.insert(0, os.path.join(ROOT, "services", "media"))
    from schema import RenderRequest
    validated = RenderRequest(**rr)
    templates = [s.visual.template for s in validated.storyboard.scenes]
    print("planned scenes:", templates)
    assert templates[0] == "hook" and templates[-1] == "cta"
    assert "features" in templates and "formats" in templates  # conversion objective
    for s in validated.storyboard.scenes:
        assert 1 <= len(s.voiceover) <= 40, s.voiceover
    print("media schema validation: PASS")

    # 3) smoke-render one frame per scene through the real engine
    import engine
    C = {"W": 1920, "H": 1080, "nscenes": len(validated.storyboard.scenes),
         "brand": {"name": "云账房", "byline": "小微企业记账"}}
    outdir = os.path.join(HERE, "fixtures", "frames")
    os.makedirs(outdir, exist_ok=True)
    for i, s in enumerate(validated.storyboard.scenes):
        f = engine.new_frame(1920, 1080, i * 5 + 3.0)
        engine.TEMPLATES[s.visual.template]["fn"](f, 3.0, s.visual.params, C)
        engine.subtitle(f, C, s.voiceover, 1.0)
        f.convert("RGB").save(os.path.join(outdir, f"scene_{i}_{s.visual.template}.png"))
    print("engine smoke render: PASS —", len(validated.storyboard.scenes),
          "frames in", outdir)
    print("ALL PASS")


if __name__ == "__main__":
    main()
