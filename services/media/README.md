# services/media — TTS 适配层 + 渲染服务 v0

storyboard JSON + 画幅列表 → 带配音/音乐/字幕的 1080p MP4，含自动 QC 与用量计量。

## 接口

| Method | Path | 说明 |
|---|---|---|
| POST | `/v1/renders` | 提交渲染任务（202，返回 job_id）|
| GET | `/v1/jobs/{id}` | 任务状态/进度/QC/计量/回填后的 storyboard |
| GET | `/v1/jobs/{id}/outputs/{aspect}` | 下载成片（aspect 如 `16x9`）|
| POST | `/v1/tts/synth` | 单句合成（返回时长 + 逐字时间戳，内容寻址缓存）|
| GET | `/health` | 健康检查 |

请求示例见 `sample_storyboard.json`（云账房虚构产品，验证模板参数化）。

## 契约要点

- `scenes[].duration_ms` 输入可空/作为最小值；执行时由 `max(模板最小值, lead + TTS实际时长 + tail)` 回填。
- `visual.template` ∈ hook / options / features / editor / formats / cta（v0 模板库，全矢量绘制，双画幅布局）。
- `visual.params` 为模板私有参数，由本服务校验；未来资产引用统一 `asset_id`，本服务不抓取任何 URL。
- TTS adapter 契约：`synth(text, voice, rate) → {audio(44.1k wav), duration, words[{word,start,end}]}`。
  已实现 `edge`（微软神经语音）与 `say`（macOS 离线兜底）；生产切火山引擎/讯飞 = 新增一个 class。

## QC（每个成片自动执行）

分辨率 / 帧率 / 时长偏差 <0.35s / 有音轨 / 采样帧非黑 / 画面有变化。任一失败 → `failed_qc`。

## 计量（job 完成后返回）

`tts_chars`、`tts_cache_hits`、`tts_wall_s`、`render_wall_s`、`output_seconds`、`output_bytes` —
对应 credits 结算模型中的内部计量项。

## 已知事项 / 路线

- **渲染进程隔离**：v0 渲染跑在 API 进程线程内。macOS 上后台进程可能被降到能效核
  （实测同一视频 149s vs 4397s），Linux 部署无此问题，但 v1 应把渲染拆成独立 worker
  进程（也符合契约里 API/worker 隔离边界）。
- 模板库扩展与 style pack 参数化（配色/字体可换）。
- 是否迁移 Remotion 在 Web MVP 接入后评估：当前 PIL 管线 872 帧 ≈ 17s（前台）已够 MVP。
- 逐字时间戳已返回，字幕卡拉OK式高亮待接入。
