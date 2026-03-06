# 05. Core API（本地引擎接口）

Base URL: `http://127.0.0.1:${CORE_PORT}`

鉴权：除 `GET /health` 外，所有接口需要 `Authorization: Bearer <JWT>`

错误：统一 `ErrorEnvelope`

## 1. `GET /health`

用途：`client` 启动后探活 `core Sidecar`。

响应：

```json
{
  "status": "ok",
  "service": "core",
  "version": "0.1.0"
}
```

## 2. `POST /api/v1/ingest`

用途：导入本地素材并生成 `AtomicClip` 与关键帧拼图。

请求：

```json
{
  "project_id": "proj_001",
  "user_id": "user_001",
  "video_path": "D:/Videos/travel_kyoto.mp4"
}
```

响应：

```json
{
  "asset": {
    "asset_id": "asset_001",
    "file_path": "D:/Videos/travel_kyoto.mp4",
    "duration_ms": 3600000
  },
  "clips": [
    {
      "clip_id": "clip_001",
      "start_ms": 12000,
      "end_ms": 16800,
      "frame_pack_base64": "<omitted>"
    }
  ],
  "stats": {
    "clip_count": 428,
    "processing_ms": 32500
  }
}
```

说明：

1. `frame_pack_base64` 仅用于上传到云端向量化，不持久化到云端对象存储。
2. 若素材过大，允许分批返回（`batch`）。

## 2.1 `POST /api/v1/ingest/jobs`

用途：创建异步切分任务，返回 `job_id`。

## 2.2 `GET /api/v1/jobs/{job_id}`

用途：查询任务状态与结果。

状态：

1. `queued`
2. `running`
3. `succeeded`
4. `failed`

## 2.3 `POST /api/v1/jobs/{job_id}/retry`

用途：手动重试失败任务（不自动重试）。

## 3. `POST /api/v1/search`

用途：本地片段检索与定位（用于云端结果回放校验或离线 fallback）。

请求：

```json
{
  "project_id": "proj_001",
  "query": "temple without people",
  "top_k": 20
}
```

响应：

```json
{
  "hits": [
    {
      "clip_id": "clip_287",
      "asset_id": "asset_001",
      "start_ms": 208000,
      "end_ms": 214500,
      "score": 0.91
    }
  ]
}
```

说明：

1. `MVP` 主召回仍走云端 `DashVector`。
2. 本接口用于本地兜底和调试，不承担主检索策略。

## 4. `POST /api/v1/render`

用途：根据 `EntroVideoProject` 生成预览流。

请求：

```json
{
  "project": {
    "contract_version": "1.0.0",
    "project_id": "proj_001"
  }
}
```

响应：

```json
{
  "preview_id": "preview_001",
  "stream_url": "http://127.0.0.1:18000/preview/preview_001.m3u8",
  "duration_ms": 30000
}
```

## 5. `POST /api/v1/export`

用途：导出最终视频（默认配置）。

请求：

```json
{
  "project_id": "proj_001",
  "preset": "default"
}
```

响应：

```json
{
  "job_id": "export_001",
  "status": "queued"
}
```

规则：

1. 导出期间拒绝并行编辑写操作。
2. `preset` 在 MVP 固定为 `default`。

## 6. `GET /api/v1/jobs/{job_id}`

用途：查询导出任务状态。

状态：

1. `queued`
2. `running`
3. `succeeded`
4. `failed`

## 7. 错误码（Core）

1. `CORE_INVALID_VIDEO_PATH`
2. `CORE_SEGMENTATION_FAILED`
3. `CORE_FRAME_EXTRACT_FAILED`
4. `CORE_RENDER_FAILED`
5. `CORE_EXPORT_LOCKED`
