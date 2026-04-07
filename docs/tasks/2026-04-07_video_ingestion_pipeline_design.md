# 视频素材处理全流程 (Video Ingestion Pipeline) 设计文档

日期：`2026-04-07`

## 1. Context (背景)

当前 `EntroCut` 已经完成了核心事实的架构和状态管理的重构（如 `2026-03-31_project_state_management_refactor_task.md` 所示），但在视频导入处理链路中，`core/store.py` 的 `_run_assets_import` 仍然使用的是 `asyncio.sleep` 模拟的占位逻辑。

为了跑通“视频素材增量上传 -> 本地切分 -> 抽帧拼接 -> 云端向量化 -> 界面响应”的真实 MVP 闭环，本设计文档详细规划了这部分基础设施的真实落地实现。该设计严格遵循：

1. **隐私安全**：云端只接触拼接好的图像和向量，绝不上传原始视频流。
2. **权威在本地**：`core` 作为桌面端中枢负责繁重的音视频处理与状态控制。
3. **状态事实化**：基于已有的 `processing_stage` (pending -> segmenting -> vectorizing -> ready/failed) 事实来驱动前端展示。

---

## 2. 整体交互时序

1. **Client (UI)**：用户拖入视频或点击导入。发起 HTTP 请求至 Core，获取 TaskID 后立即在素材库（Asset Panel）展示带加载态的骨架缩略图。
2. **Core (Engine)**：
   - 接收本地文件路径，落库初始 Asset（状态 `pending`）。
   - 启动异步导入 Task，向 Client 推送 `asset.updated` 和 `task.updated`。
   - 调用 `PySceneDetect` 进行硬切分。
   - 借助 `ffmpeg-python` 和 `Pillow` 进行抽帧、拼接并转 Base64。
   - 发送 Base64 列表到 Server 换取向量。
3. **Server (Gateway)**：
   - 接收 Base64 组，调用阿里云多模态模型获取 1024 维 Embedding。
   - 存入 DashVector 并返回插入成功结果。
4. **Core (Engine)**：收到成功响应后，将切片 `ClipModel` 落入本地 `SQLite` 库并绑定到 `EditDraft`，将 Asset 置为 `ready`，再发一次 WebSocket 广播。
5. **Client (UI)**：监测到 `ready` 事件，刷新视图并取消加载态，正常展示视频缩略图和可用的候选 Clip 数量。

---

## 3. 详细设计：各端改动点

### 3.1 客户端 (Client) - 骨架与流转呈现

**现状**：`useWorkspaceStore.ts` 中已经消费了 `processingStage` 和 `processingProgress` 字段。
**改动点**：
1. **占位与 Skeleton (骨架屏)**：
   - 在 Workspace 的素材管理组件中，如果 `asset.processingStage !== 'ready'` 并且不是 `'failed'`，在原有的缩略图区域显示一个转圈或进度条，辅以对应的中文状态文本（如：`segmenting` -> "镜头切分中...", `vectorizing` -> "云端特征提取中..."）。
2. **错误处理展示**：
   - 监听若 `processingStage === 'failed'`，显示一个重试 Icon，Hover 时可展示 `asset.lastError` 中的错误明细。
3. **首帧 / 缩略图对接**：
   - 处理完后（`ready`），可以通过 Core 返回的 `source_path` 搭配自定义本地协议（通过 Electron Bridge）来提取并展示一张正常缩略图。

### 3.2 本地引擎 (Core) - 重型算力与管线落地

**现状**：`store.py` 内部 `_run_assets_import` 有 mock 的状态机转移。
**改动点**：

1. **依赖引入**：
   - 修改 `core/requirements.txt`，添加 `scenedetect[opencv]`, `ffmpeg-python`, `Pillow`。

2. **新建算力模块 `core/ingestion.py`** (或 `core/services/ingestion.py`)：
   - 负责封装所有无状态（Stateless）处理函数，隔离业务与库：
   - `detect_scenes(video_path) -> list[tuple[int, int]]`：返回毫秒级的 `start_ms`, `end_ms` 列表。
   - `extract_and_stitch_frames(video_path, start_ms, end_ms) -> str`：抽取指定时间段的 4 帧，拼成 `2x2`，角落加数字水印，最终返回 UTF-8 的 Base64 字符串 `image_base64`。

3. **重构 `store.py::_run_assets_import`**：
   - **Segmenting 阶段**：对每个传入的 `media_ref`，调用 `detect_scenes`。利用生成的 Scene List 创建初始的 `ClipModel` (此时只含有时间范围，尚无特征)。
   - **Vectorizing 阶段**：遍历 `ClipModel` 列表，分批 (Batching) 调用 `extract_and_stitch_frames`。将构造好的 Base64 Payload 拼接成 `VectorizeRequest`。
   - **云端强依赖调用**：从 `auth_session_store` 中拿 Token，向云端 Server 发起 `POST /v1/assets/vectorize` 请求。
   - **写库与发事件 (Ready 阶段)**：校验结果后，将包含完整属性的 `Clip` 合并进当前 Project 的 `EditDraft`，持久化至 SQLite，并利用 `self.emit()` 通知 `Client`。

### 3.3 云端网关 (Server) - 当前链路保持稳定

**现状**：`server/app/services/vector.py` 的接口 `/v1/assets/vectorize` 已经可以调用 DashScope 和 DashVector，并以 `project_id` 为字段实现了租户隔离。
**改动点**：
- **无需改动**。Server 端现有的 Vector 接入及入库逻辑结构已经完备。Core 端只需要按现有的 `VectorizeRequest` 契约精准投递即可。如果请求量大，建议 Core 控制 `Batch Size` (例如每次请求包含 10 个 clip docs) 以防止 Request Body 过大或云端限流报错。

---

## 4. Action Items (执行步骤)

为了不引起大的代码冲突与回归，建议分 3 个 PR 稳步推进：

- [ ] **PR 1 (核心算力层)**：在 `core` 中引入依赖，开发 `ingestion.py`。包含本地视频切分测试与 2x2 多帧拼接图片生成的独立单元测试。
- [ ] **PR 2 (状态调度层)**：重构 `core/store.py` 的 `_run_assets_import`。接入真实的 ingestion 服务，替换 `asyncio.sleep`。实现 HTTP 调用并处理失败回调，更新状态机制。
- [ ] **PR 3 (前端展示层)**：在 `client` 端对接新的 Loading 态。在素材列表区域正确渲染 `processing_stage` 的流转进度（`segmenting` -> `vectorizing` -> `ready`/`failed`），完善重试与异常报错展示。

## 5. 风险与缓解 (Risks & Mitigations)

1. **长时间占用主线程 (GIL Block)**：
   - *问题*：音视频处理（OpenCV/FFmpeg）若是同步调用，会阻塞 FastAPI 甚至 WebSocket 事件循环。
   - *缓解*：`detect_scenes` 和 FFmpeg 抽帧等耗时方法必须包裹在 `asyncio.to_thread()` 中执行，保证 Core 在处理时仍能持续响应 Client 的 Chat 和心跳包。
2. **大视频文件的内存爆炸**：
   - *问题*：如果要一次性抽取几百个 Clip 的 4 帧缓存并在内存拼接图片，可能撑爆桌面端内存。
   - *缓解*：严格实行分页（Paging / Batching）。处理完 10 个 Clip 就发起一次 Vectorize HTTP 动作并释放 Base64 缓存。
