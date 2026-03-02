# 03. Domain Model（领域模型）

## 1. 核心实体

| Entity（实体） | Owner（归属） | 说明 | 关键字段 |
|---|---|---|---|
| `User` | `server` | 用户身份与隔离边界 | `user_id` |
| `Project` | `client` | 一个剪辑工程容器 | `project_id`, `name`, `status` |
| `SourceAsset` | `core/client` | 用户导入的原始素材 | `asset_id`, `file_path`, `duration_ms` |
| `AtomicClip` | `core` | 镜头切分后的最小可检索单位 | `clip_id`, `asset_id`, `start_ms`, `end_ms` |
| `ClipFramePack` | `core -> server` | 每镜头 4 帧拼图输入 | `clip_id`, `image_base64`, `frame_index_marks` |
| `ClipEmbeddingRecord` | `server` | 云端向量索引记录 | `vector`, `user_id`, `file_path`, `time_range` |
| `RetrievalCandidate` | `server` | 语义检索候选结果 | `clip_id`, `score`, `reason` |
| `EntroVideoProject` | `shared` | 共享剪辑契约 | `contract_version`, `timeline`, `reasoning` |
| `TimelineTrack` | `shared` | 时间线轨道 | `track_id`, `track_type` |
| `TimelineItem` | `shared` | 轨道上的片段实例 | `item_id`, `source_clip_id`, `timeline_start_ms`, `filters` |
| `ChatSession` | `server/client` | 多轮对话容器 | `session_id`, `project_id` |
| `ChatTurn` | `server/client` | 单轮对话记录 | `turn_id`, `role`, `content`, `timestamp` |
| `RenderPreview` | `core/client` | 当前预览产物 | `preview_id`, `stream_url`, `generated_at` |

## 2. 关系约束

1. 一个 `Project` 可包含多个 `SourceAsset`。
2. 一个 `SourceAsset` 会切分成多个 `AtomicClip`。
3. 一个 `AtomicClip` 对应一条 `ClipEmbeddingRecord`（可重建）。
4. `TimelineItem.source_clip_id` 必须引用现存 `AtomicClip`。
5. `ChatSession` 与 `Project` 一一关联。
6. `EntroVideoProject` 是当前可编辑状态的唯一事实源（`Single Source of Truth`）。

## 3. 状态约束（MVP）

1. `Timeline` 不引入显式 `State Machine（状态机）`。
2. 用户可无限修改，系统按“最新契约覆盖”处理。
3. 导出动作单独加锁，不影响契约模型定义。

## 4. 扩展位（保留不实现）

1. `Multi-User Interface（多用户接口）`
   1. `owner_user_id`
   2. `collaborator_ids`
   3. `permission_scope`
2. `Agent Tool/Skill（智能体工具/技能）`
   1. `tool_name`
   2. `tool_args`
   3. `tool_result_ref`
