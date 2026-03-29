# Server Retrieve / Inspect Gateway Design

本文档定义当前阶段 `Server` 在 `retrieve / inspect` 链路中的稳健落地方案。

它解决的问题是：

1. `Core` 在本地持有素材与 `EditDraft`
2. 阿里云 `embedding`、`DashVector`、`Gemini` 等能力都只能经由云端 `Server`
3. 当前没有稳定可用的视频理解模型
4. `Server` 已经部署在云端，方案必须能平滑增量上线

所以本文档的目标不是追求“理论最强”，而是定义：

`当前阶段最稳、最可落地、最不容易把后面架构锁死的 retrieve / inspect 云端网关方案。`

如果要直接看字段级契约草案，请继续阅读：

1. [06b_server_vectorize_contract.md](./06b_server_vectorize_contract.md)
2. [06c_server_retrieval_contract.md](./06c_server_retrieval_contract.md)
3. [06d_server_inspect_contract.md](./06d_server_inspect_contract.md)

---

## 1. 设计结论

当前推荐方案是：

1. `planner` 继续走 `POST /v1/chat/completions`
2. `retrieve` 走专用 `vectorize / retrieval` 网关
3. `inspect` 走专用 `keyframe-sequence inspect` 网关
4. `preview` 完全留在本地 `Core`
5. `Server` 负责模型与向量服务中转，不负责媒体处理与草案状态

一句话：

`Core` 管媒体与工程状态，`Server` 管云端能力与鉴权配额；当前阶段用纯 embedding 做 retrieve，用多关键帧序列 + Gemini 做 inspect。

---

## 2. 为什么这是当前最稳的方案

### 2.1 不选择“全部走通用 chat/completions”

如果把 `inspect` 也塞进通用 `/v1/chat/completions`：

1. 专用工具边界会塌
2. 候选图片会挤占主 `planner` 上下文
3. 结果难校验、难缓存、难观测
4. `planner` 和“眼睛”会过度耦合

所以：

`/v1/chat/completions` 只服务 planner 与开放式对话，不服务专用 inspect。

### 2.2 不等待“真正的视频理解模型”

等待视频理解模型会把工程推进完全卡死。

更现实的做法是：

1. 接受当前阶段无法稳定理解整段视频
2. 为每个候选 `clip` 提供按时间顺序排列的关键帧序列
3. 同时附带每帧在片段内的位置时间和片段总时长
4. 用图像级多模态判断完成 `inspect`

这不是终局，但足够支撑：

1. 候选比较
2. 开头/转场/替换镜头粗判
3. `choose / compare / rank / verify`

### 2.3 不把更多媒体处理搬到云端

如果让 `Server` 做抽帧、拼图、预览渲染：

1. 需要上传更多原始媒体
2. 隐私和带宽成本会上升
3. 云端会被迫承载工程状态与媒体处理
4. 与当前 `Core-heavy` 架构冲突

所以：

`Server` 当前只做能力网关，不做媒体处理引擎。

---

## 3. 最终职责划分

### 3.1 Client

只负责：

1. 用户交互
2. 可视化 `EditDraft`
3. 展示候选、预览、对话和通知

### 3.2 Core

负责：

1. 素材切分
2. 关键帧抽取
3. 检索用 `contact sheet` 生成
4. `inspect` 用多关键帧序列准备
5. `EditDraft` 持有与 patch 应用
6. 本地 `preview`
7. `planner` 上下文拼装
8. 调用 `Server` 的专用工具接口

### 3.3 Server

负责：

1. `JWT` 鉴权
2. 额度与限流
3. `planner` 大模型中转
4. `embedding` 能力中转
5. `DashVector` 检索中转
6. `inspect` 图像判定中转
7. 能力探针与结构化错误语义

### 3.4 明确非目标

`Server` 当前不负责：

1. 原始视频存储
2. 视频抽帧
3. `EditDraft` 持久化
4. 本地预览渲染
5. 完整视频理解

---

## 4. Phase 1 Retrieve 方案

### 4.1 表征对象

`retrieve` 的检索对象固定为 `clip`。

每个 `clip` 在本地被压缩成一个 `contact sheet`：

1. 由 `Core` 对每个 `clip` 抽取 4 帧或 6 帧
2. 本地拼成一张小图
3. 这张图成为 `clip` 的当前阶段主检索表征

### 4.2 为什么用 `contact sheet`

因为它同时满足：

1. 比视频更便宜
2. 比单帧更能表达时序变化
3. 可直接走当前阿里云多模态 `embedding`
4. 可复用于后续 `inspect`

### 4.3 向量化入口

当前推荐接口继续使用：

1. `POST /v1/assets/vectorize`
2. 输入对象改为：`clip contact sheet`

推荐请求载荷：

```json
{
  "collection_name": "entrocut_assets",
  "partition": "default",
  "model": "qwen3-vl-embedding",
  "dimension": 1024,
  "docs": [
    {
      "id": "clip_001",
      "content": {
        "image_base64": "..."
      },
      "fields": {
        "clip_id": "clip_001",
        "asset_id": "asset_001",
        "project_id": "proj_001",
        "source_start_ms": 1200,
        "source_end_ms": 4800
      }
    }
  ]
}
```

设计原则：

1. `phase 1` 的主输入是 `image_base64`
2. 不上传原始视频
3. 不要求默认同时带 `text + image + video`
4. `fields` 只保留检索回写真正需要的元数据

### 4.4 为什么不用视频输入

不是因为阿里云不能处理视频，而是因为当前阶段不值得：

1. 请求体更大
2. 成本更高
3. 失败面更宽
4. 与当前 `Core` 本地媒体处理策略冲突

所以当前结论是：

`vectorize phase 1 只吃 contact sheet image，不吃原视频。`

### 4.5 检索入口

继续使用：

1. `POST /v1/assets/retrieval`

当前只支持：

1. `query_text`
2. `topk`
3. 搜索空间边界 `filter`

不支持：

1. `query_image`
2. `query_video`
3. 多 query 合并
4. 服务端 rerank

### 4.6 召回结果

`Server` 只返回：

1. `clip_id`
2. `asset_id`
3. `score`
4. 最小必要元数据

它不负责：

1. 最终候选选择
2. 二次深理解
3. 草案级编排

---

## 5. Phase 1 Inspect 方案

### 5.1 核心结论

当前没有稳定可用的视频理解模型时，`inspect` 直接收敛为：

`ordered keyframe inspection（有序关键帧判定）`

也就是：

1. `Core` 为候选 `clip` 准备多张关键帧图
2. 关键帧按时间顺序发送
3. 每张关键帧附带在片段内的位置时间
4. 同时附带片段总时长
5. `Core` 发起专用 `inspect` 请求
6. `Server` 调 `Gemini` 之类图像多模态模型
7. `Server` 返回结构化 `InspectionObservation`

### 5.2 为什么要单独做专用接口

因为 `inspect` 是工具，不是开放式对话。

它需要：

1. 小候选集
2. 强结构化输出
3. 并行与缓存空间
4. 独立错误语义

所以当前推荐新增：

1. `POST /v1/tools/inspect`

而不是让 `Core` 把图片和问题塞进 `/v1/chat/completions`。

### 5.3 推荐请求

```json
{
  "mode": "choose",
  "task_summary": "为 opening scene 选择更有出发感的镜头",
  "hypothesis_summary": "旅程开始通常表现为收拾行李、走向车站、交通工具启动",
  "question": "在这些候选里，哪个最适合作为旅行视频的开头？",
  "candidates": [
    {
      "clip_id": "clip_001",
      "asset_id": "asset_001",
      "clip_duration_ms": 4200,
      "frames": [
        { "frame_index": 0, "timestamp_ms": 0, "timestamp_label": "00:00", "image_base64": "..." },
        { "frame_index": 1, "timestamp_ms": 1100, "timestamp_label": "00:01.1", "image_base64": "..." },
        { "frame_index": 2, "timestamp_ms": 2600, "timestamp_label": "00:02.6", "image_base64": "..." },
        { "frame_index": 3, "timestamp_ms": 4100, "timestamp_label": "00:04.1", "image_base64": "..." }
      ]
    },
    {
      "clip_id": "clip_002",
      "asset_id": "asset_001",
      "clip_duration_ms": 3900,
      "frames": [
        { "frame_index": 0, "timestamp_ms": 0, "timestamp_label": "00:00", "image_base64": "..." },
        { "frame_index": 1, "timestamp_ms": 900, "timestamp_label": "00:00.9", "image_base64": "..." },
        { "frame_index": 2, "timestamp_ms": 2200, "timestamp_label": "00:02.2", "image_base64": "..." },
        { "frame_index": 3, "timestamp_ms": 3800, "timestamp_label": "00:03.8", "image_base64": "..." }
      ]
    }
  ]
}
```

### 5.4 推荐响应

```json
{
  "question_type": "choose",
  "selected_clip_id": "clip_002",
  "ranking": ["clip_002", "clip_001"],
  "candidate_judgments": [
    {
      "clip_id": "clip_001",
      "verdict": "partial_match",
      "confidence": 0.62,
      "short_reason": "有出发感，但主体动作不够明确"
    },
    {
      "clip_id": "clip_002",
      "verdict": "match",
      "confidence": 0.84,
      "short_reason": "主体动作更明确，更像旅程开始"
    }
  ],
  "uncertainty": null
}
```

### 5.5 当前能力边界

`inspect phase 1` 只保证：

1. `verify`
2. `compare`
3. `choose`
4. `rank`

它不保证：

1. 连续动作精细理解
2. 长视频时序理解
3. 高审美精剪判断

如果关键帧序列不足以支撑判断，允许返回：

1. `DECISION_INCONCLUSIVE`

而不是硬判。

---

## 6. Runtime Capabilities 设计

`Core` 不应假设所有云端能力始终可用。

因此建议把 `GET /api/v1/runtime/capabilities` 扩成可执行能力探针：

```json
{
  "service": "server",
  "version": "0.7.0",
  "capabilities": {
    "planner_chat": { "available": true },
    "multimodal_embedding": { "available": true, "model": "qwen3-vl-embedding" },
    "vector_retrieval": { "available": true, "provider": "dashvector" },
    "inspect_image": { "available": true, "provider": "gemini", "mode": "ordered_keyframes" },
    "inspect_video": { "available": false, "reason": "not_enabled_in_phase_1" }
  }
}
```

这样 `Core` 才能做稳定分支：

1. 能不能检索
2. 能不能做图像级 `inspect`
3. 是否必须跳过 `inspect`

---

## 7. 云端已部署条件下的上线策略

既然 `Server` 已经在云端运行，这次方案必须增量上线，不能打断现有主链。

### 7.1 不破坏已有接口

保留：

1. `POST /v1/chat/completions`
2. `POST /v1/assets/vectorize`
3. `POST /v1/assets/retrieval`

新增：

1. `POST /v1/tools/inspect`

### 7.2 先加能力，再让 Core 使用

顺序建议：

1. 先上线 `capabilities.inspect_image`
2. 再上线 `/v1/tools/inspect`
3. 最后让 `Core` 在能力存在时切到真实 `inspect`

### 7.3 允许显式降级

如果 `inspect_image` 不可用：

1. `Core` 不应崩溃
2. 可以走：
   - 文本摘要 fallback
   - 直接要求用户确认
   - 停在候选池，不自动 patch

这比把失败藏在链路内部稳得多。

---

## 8. 传输与成本控制

### 8.1 当前推荐

1. `vectorize` 走小批量 `image_base64`
2. `inspect` 走小候选集多关键帧 `image_base64`
3. 图片统一压到适合判定的低清 `JPEG`

### 8.2 为什么当前不引入对象存储

因为对象存储会显著增加：

1. 上传协议复杂度
2. 临时生命周期管理
3. 云端存储边界问题

当前阶段直接小图内联请求更简单，也足够支撑：

1. `vectorize`
2. 小规模 `inspect`

等请求规模真的成为瓶颈，再引入临时对象存储。

---

## 9. 文档级统一口径

从现在开始，`Server` 侧文档统一采用以下口径：

1. `planner` 走 `OpenAI-compatible /v1/chat/completions`
2. `retrieve` 走专用 `/v1/assets/vectorize + /v1/assets/retrieval`
3. `inspect` 走专用 `/v1/tools/inspect`
4. `preview` 不属于 `Server`
5. `inspect_video` 当前不可用，`inspect_image` 的当前稳定形态是“有序关键帧序列”

---

## 10. 一句话结论

当前最稳的云端方案不是等待“真正的视频理解模型”，而是：让 `Core` 在本地完成切分与关键帧抽取，让 `Server` 作为云端能力网关承接 `embedding / DashVector / Gemini`，用纯向量召回做 `retrieve`，用“多关键帧 + 时间位置 + 片段总时长”的图像序列判定做 `inspect`，同时通过 `capabilities` 和专用工具接口把能力边界表达清楚。
