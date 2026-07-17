# sjms — 神机妙述 (s-j.ai)

AI 产品介绍视频生成服务：网址 / 截图 / 录屏 → 可编辑 storyboard → 多画幅成片。
by 神机AI。

## 仓库结构

```
contracts/          # 版本化契约（Storyboard / ProductUnderstanding JSON Schema, OpenAPI）— owner: Cindy
docs/               # PRD 与设计文档 — owner: Cindy
services/media/     # TTS 适配层 + 渲染服务（storyboard → mp4）— owner: Bob
web/                # script-first Web MVP（Next.js，规划中）— owner: Cindy
```

## 核心原则

1. **storyboard JSON 是唯一事实源** — 横版/竖版/方形只是同一份数据的不同渲染结果。
2. **镜头时长由 TTS 实际时长回填**（`durationMs` 请求可不填，执行时写回）。
3. **渲染层不接触原始输入** — 只吃模板名 + 文本参数 + 已解析的 assetId。
4. **供应商可插拔** — TTS/理解模型按 adapter 接入，全链路记录用量（内部 token/字符/秒计量，对外 credits）。

## 快速开始（渲染服务）

```bash
cd services/media
pip install -r requirements.txt   # 另需系统 ffmpeg
uvicorn app:app --host 0.0.0.0 --port 8787
curl -X POST localhost:8787/v1/renders -H 'Content-Type: application/json' \
  -d @sample_storyboard.json
```

详见 `services/media/README.md`。

## 部署形态（MVP）

家庭服务器单机 docker-compose：nginx + web + api + postgres + workers；
公网入口经小型 VPS 反代/穿透（详见 `docs/mvp-prd-v0.1.md` 部署章节）。
