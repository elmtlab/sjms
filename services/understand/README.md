# services/understand — 理解 worker v0

截图（已解析的本地 artifact）→ 视觉模型 → `ProductUnderstanding v0.1` → 规则 planner → 可直接投递给 `services/media` 的渲染请求 JSON。

## 接口

| Method | Path | 说明 |
|---|---|---|
| POST | `/v1/understand` | sources + artifactPaths + hints → ProductUnderstanding（含 provider/model/prompt_version 元信息）|
| POST | `/v1/plan` | ProductUnderstanding + brand 快照 → 渲染请求 JSON |
| POST | `/v1/pipeline` | 一次调用完成 understand + plan |
| GET | `/health` | 健康检查 |

## 模型 adapter（`vlm.py`）

| provider | 模型 | 凭证 env |
|---|---|---|
| `mock` | 确定性 fixture，无网络无 key | — |
| `glm` | 智谱 GLM-4V（默认 glm-4v-flash）| `ZHIPU_API_KEY` |
| `qwen` | 通义 Qwen-VL（DashScope）| `DASHSCOPE_API_KEY` |
| `claude` | Anthropic Claude 视觉 | `ANTHROPIC_API_KEY` |
| `openai` | GPT-4o 视觉 | `OPENAI_API_KEY` |

统一抽取 prompt（`PROMPT_VERSION = extract-v1`）要求模型只输出 JSON：
productName / problem / valueProposition / claims（含截图序号 + 原文摘录做证据）/ features。
`_mk_understanding` 归一化为契约格式；claims 上限 5、features 上限 4，超长截断。

## 规则 planner（`planner.py`）

确定性、可测试；后续 LLM planner 用同一 `plan()` 签名替换。
按 objective 选场景：hook（总是）→ options（onboarding）→ features（总是，claims 按
confidence 取前 3，证据入画）→ formats（launch/conversion）→ cta（总是）。
旁白逐句 ≤40 字（配合 TTS 节奏带）。

## 边界（与契约一致）

- 输入是**已解析的本地 artifact 路径**（单机部署下由 Web 上传层落盘）；本服务不抓取 URL。
- 输出的 understanding 通过 `contracts/product-understanding.schema.json` 校验；
  planner 输出通过 `services/media/schema.py` 校验。

## 测试

```bash
python3 test_pipeline.py
# 生成假截图 → mock 理解 → 契约 schema 校验 → planner → media schema 校验
# → 真实 engine 逐场景渲帧冒烟。无需网络与 key。
```
