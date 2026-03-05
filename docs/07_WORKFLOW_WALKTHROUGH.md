# 07. Workflow Walkthrough（流程走查）

## 场景零：启动台进入工作台（Launchpad Entry）

1. 用户打开客户端，默认进入 `Launchpad`。
2. 用户可选择两种启动方式：
   1. 拖入素材文件夹到 `Intent Drop-Zone`。
   2. 输入 Prompt 并创建新项目。
3. 用户也可点击 `Recent Workspaces` 卡片直接回到历史项目。
4. 页面进入 `Workspace` 后开始后续摄入、对话、渲染链路。

验收点：

1. 启动台可见项目 AI 状态（如 `Analyzed x clips`、`Last AI Edit`）。
2. 启动路径与工作台路径切换稳定，无页面状态错乱。

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
2. `client -> server`: `POST /api/v1/chat`。
3. `server` 执行：
   1. `Context Engineering`（上下文工程）。
   2. `Intent Classification`（意图判断）。
   3. `Logic Routing`（逻辑路由）。
   4. 语义检索与契约生成。
4. `client -> core`: `POST /api/v1/render`。
5. `core` 返回 `preview stream`，用户可播放预览。

验收点：

1. 返回内容必须是结构化契约，不是自然语言片段列表。
2. `reasoning` 在界面可展示。

## 场景三：语义微调（Refinement）

1. 用户选中某片段输入：“这个镜头有人，换成没人且构图更好看。”
2. `client -> server`: `POST /api/v1/chat`（携带选中片段上下文与当前契约）。
3. `server` 在接口内部完成意图判断并返回 `patch` 或更新后的 `project`。
4. `client` 应用 `patch` 更新本地契约。
5. `client -> core`: 触发重渲染，预览实时更新。

验收点：

1. 不要求复杂时间线编辑器能力。
2. 微调路径必须全链路可重复。

## 时延预算（MVP）

1. Ingest（1 小时素材）：`<= 60s` 首次可检索。
2. Chat 首轮请求：`<= 10s` 返回第一版契约。
3. Chat 微调请求：`<= 6s` 返回替换方案或契约补丁。
4. Render 预览启动：`<= 5s` 开始播放。
