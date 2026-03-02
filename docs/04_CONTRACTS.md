# 04. Contracts（契约）

## 1. 契约目标

`EntroVideoProject` 是 `client/server/core` 共享的数据契约，负责承载：

1. AI 生成的剪辑结构。
2. 用户可编辑状态。
3. 预览与导出的输入。

## 2. 契约治理

1. 契约版本字段：`contract_version`（例如 `1.0.0`）。
2. `Minor（次版本）`：向后兼容新增字段。
3. `Major（主版本）`：删除字段或语义变更。
4. 任何 `Major` 变更必须同时更新三端校验模型：
   1. `client`: TypeScript Interface（类型接口）
   2. `server`: Pydantic Model（数据模型）
   3. `core`: Dataclass / Pydantic（数据模型）

## 3. `EntroVideoProject` MVP 结构

```json
{
  "contract_version": "1.0.0",
  "project_id": "proj_001",
  "user_id": "user_001",
  "updated_at": "2026-03-02T10:30:00Z",
  "assets": [
    {
      "asset_id": "asset_001",
      "file_path": "D:/Videos/travel_kyoto.mp4",
      "duration_ms": 3600000
    }
  ],
  "clip_pool": [
    {
      "clip_id": "clip_001",
      "asset_id": "asset_001",
      "start_ms": 12000,
      "end_ms": 16800,
      "embedding_ref": "vec_001"
    }
  ],
  "timeline": {
    "tracks": [
      {
        "track_id": "v1",
        "track_type": "video",
        "items": [
          {
            "item_id": "item_001",
            "source_clip_id": "clip_001",
            "timeline_start_ms": 0,
            "source_in_ms": 0,
            "source_out_ms": 4800,
            "filters": {
              "speed": 1.0,
              "volume_db": 0.0
            },
            "reasoning": "保留寺庙空镜，构图稳定，符合宁静主题。"
          }
        ]
      }
    ]
  },
  "reasoning_summary": "整体采用慢节奏空镜和低运动镜头。"
}
```

## 4. 字段约束

1. `filters`（MVP）仅支持：
   1. `speed`
   2. `volume_db`
2. `reasoning` 为必填字段，不允许空字符串。
3. `file_path` 仅作为定位本地素材的引用，非云端存储对象。
4. 所有时间字段统一 `ms（毫秒）`。

## 5. 通用错误契约

```json
{
  "error": {
    "code": "SERVER_VECTOR_TIMEOUT",
    "message": "Vector service timeout.",
    "details": {
      "request_id": "req_123",
      "retryable": true
    }
  }
}
```

规则：

1. `code` 必须可枚举、可分支处理。
2. `message` 面向调用方，可读但不泄露内部实现。
3. `details` 只放排障必要信息。
