# 07. Workflow Walkthrough（流程走查）

## 场景一：冷启动与素材摄入（Ingestion）

1. 用户在 `client` 导入 `travel_kyoto.mp4`。
2. `client -> core`: `POST /api/v1/ingest`。
3. `core` 执行：
   1. `PySceneDetect` 镜头切分。
   2. 每镜头 4 帧抽样 + 拼图。
4. `client/core -> server`: `POST /api/v1/index/upsert-clips`（向量化入库）。
5. `server` 写入 `DashVector`（强制 `user_id` 过滤键）。
6. `client` 更新素材状态为 `Ready`。

验收点：

1. 无视频文件上传云端。
2. 能得到可检索 `AtomicClip` 列表。

## 场景二：意图编排与初剪（Orchestration）

1. 用户输入：“帮我剪一个 30 秒京都宁静视频，慢节奏。”
2. `client -> server`: `POST /api/v1/agent/plan`。
3. `server` 执行：
   1. 意图理解。
   2. 语义检索。
   3. 生成 `EntroVideoProject` + `reasoning`。
4. `client -> core`: `POST /api/v1/render`。
5. `core` 返回 `preview stream`，用户可播放预览。

验收点：

1. 返回内容必须是结构化契约，不是自然语言片段列表。
2. `reasoning` 在界面可展示。

## 场景三：语义微调（Refinement）

1. 用户选中某片段输入：“这个镜头有人，换成没人且构图更好看。”
2. `client -> server`: `POST /api/v1/agent/refine`（携带选中片段上下文）。
3. `server` 返回 `patch` 与替换理由。
4. `client` 应用 `patch` 更新本地契约。
5. `client -> core`: 触发重渲染，预览实时更新。

验收点：

1. 不要求复杂时间线编辑器能力。
2. 微调路径必须全链路可重复。

## 时延预算（MVP）

1. Ingest（1 小时素材）：`<= 60s` 首次可检索。
2. Plan 请求：`<= 10s` 返回第一版契约。
3. Refine 请求：`<= 6s` 返回替换方案。
4. Render 预览启动：`<= 5s` 开始播放。
