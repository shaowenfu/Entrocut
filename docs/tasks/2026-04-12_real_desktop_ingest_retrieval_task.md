# EntroCut 桌面端真实视频导入与检索链路收敛任务文档

日期：`2026-04-12`

## 1. 北极星目标

把 `EntroCut` 当前“半真实、半占位”的素材导入链路，收敛成一条唯一可信的生产级主链：

`Browse Folder -> 扫描本地视频文件 -> files[path] -> core ingest -> scene detect -> contact sheet -> server vectorize -> DashVector write -> retrieval_ready`

北极星标准只有一条：

`用户在真实 Electron 应用中选择一个本地素材目录后，系统不复制原始视频文件，只基于本地 source path 完成真实切分与向量化，并让后续 agent retrieve/inspect 只消费真实召回结果。`

---

## 2. 当前问题

当前仓库里，和“真实视频导入与召回”相关的能力并不是单一路径，而是三条语义不同的路径混在了一起：

1. `Launchpad` 带媒体创建项目时，走 `create_project(payload.media)`，会直接生成 fake `assets/clips`
2. `Workspace` 页内上传素材时，走 `assets:import`，这条路径才会进入真实 `core ingest`
3. `Electron` 当前只暴露“选目录”能力，但 `core` 把 `folder_path` 当成单个媒体文件路径使用

这三件事叠加后，导致系统存在 4 个结构性断点：

### 2.1 fake clips 仍然污染主流程

当前 [core/store.py](/home/sherwen/MyProjects/Entrocut_server/core/store.py:446) 的 `create_project` 会直接调用 [core/helpers.py](/home/sherwen/MyProjects/Entrocut_server/core/helpers.py:166) 的 `_draft_from_payload`。

而 `_draft_from_payload` 会：

1. `_build_assets`
2. `_build_clips`
3. `_mark_assets_ready`

也就是说：

1. 没有真实 `scene detect`
2. 没有真实 `vectorize`
3. 没有真实 `DashVector insert`
4. 却提前得到了 `ready assets + fake clips`

这直接破坏了系统事实层。

### 2.2 `folder_path` 契约错误

当前 `Electron` 入口返回的是目录路径，但 [core/helpers.py](/home/sherwen/MyProjects/Entrocut_server/core/helpers.py:67) 会把这个目录路径包装成一个伪造的 `MediaFileReference`：

1. `name=<folder>.mp4`
2. `path=<folder_path>`

随后真实 ingest 在 [core/store.py](/home/sherwen/MyProjects/Entrocut_server/core/store.py:685) 直接对 `asset.source_path` 调 `detect_scenes`。

这意味着当前系统把“目录”错当成“视频文件”。

### 2.3 auth gating 放得太晚

当前 `assets:import` 在 [core/routers/projects.py](/home/sherwen/MyProjects/Entrocut_server/core/routers/projects.py:48) 没有前置校验登录态。

但真实向量化前，`core` 才在 [core/store.py](/home/sherwen/MyProjects/Entrocut_server/core/store.py:745) 检查 `auth_session_store`。

结果是：

1. 任务已经进入 `segmenting`
2. 甚至已经生成本地 clips
3. 最终才在 `vectorizing` 阶段失败

这不是稳定契约。

### 2.4 Browser 调试语义污染了 Desktop 主契约

当前 `client` 的媒体输入模型同时支持：

1. `folderPath`
2. `files: File[]`

但真实 `core ingest` 的前提是：必须拿到可供 Python 直接读取的 `absolute source path`。

标准浏览器的 `File` 不保证存在可信的 `path` 字段，因此这条能力不能作为生产主契约的一部分。

---

## 3. 本任务要解决的核心问题

本任务不是“让上传看起来更像真的”，而是要回答并落地这 5 个系统级问题：

1. `EntroCut` 的唯一真实素材导入入口是什么？
2. `Client -> Core` 的最小稳定 `Schema` 是什么？
3. `Core` 应该如何表达“目录扫描”和“媒体分析”的边界？
4. `EditDraft` 里什么是事实，什么不能再由占位逻辑伪造？
5. `retrieval_ready` 如何只由真实索引成功派生，而不再被 fake 数据误触发？

一句话：

`本任务要把“真实本地素材引用式导入”升级成系统唯一可信事实源。`

---

## 4. 明确 Non-goals

本任务明确不做以下事情：

1. 不引入“复制原始视频到应用私有目录”的素材管理方案
2. 不在这一轮支持纯 Web 的生产级视频导入
3. 不在这一轮实现代理视频（proxy video）生成
4. 不在这一轮改造 `retrieve/inspect` 的排序策略本身
5. 不在这一轮改动 `server` 的多模态向量模型选择逻辑
6. 不在这一轮做时间线编辑器或渲染管线重构

这轮任务的边界非常明确：

`只收敛桌面端真实导入与真实检索准备链路。`

---

## 5. 目标契约

### 5.1 唯一真实入口

从本任务完成后开始，系统中只有两类合法项目创建方式：

1. `create empty project`
2. `create project -> then import assets`

禁止再存在“创建项目时顺便伪造 clips 并置 ready”的路径。

也就是说：

1. `create_project` 负责创建空的 `project + edit_draft`
2. `assets:import` 负责引入真实媒体事实
3. 所有 `clips` 都必须来自真实 ingest

### 5.2 `MediaReference` 目标语义

`MediaReference` 的生产契约必须收敛到：

1. `files[]` 是真实 ingest 的唯一标准输入
2. 每个条目最少包含：
   - `name`
   - `path`
3. `path` 必须是 `absolute local file path`

`folder_path` 不能再被下游当成“媒体文件路径”直接消费。

如果保留 `folder_path`，它也只能表达：

`一个待扫描的目录描述`

而不能表达：

`一个可直接送入 ffmpeg/scenedetect 的视频文件`

### 5.3 `Asset` / `Clip` 事实语义

本任务完成后：

1. `Asset`
   - 表示用户选中的真实本地媒体文件
   - 权威字段是 `source_path`
2. `Clip`
   - 表示从某个 `asset` 上分析得到的候选时间区间
   - 权威字段是 `asset_id + source_start_ms + source_end_ms`
3. `indexed_clip_count`
   - 只能表示已成功写入向量库的真实 clip 数

禁止再出现以下情况：

1. `asset.processing_stage == ready` 但从未经过 `vectorize`
2. `retrieval_ready == true` 但底层没有真实写入 `DashVector`
3. `clips` 来自占位生成，而不是 ingest

### 5.4 auth gating 目标语义

如果当前操作的最终目标包含 `server vectorize`，那系统必须在入口阶段就能稳定回答：

1. 当前是否已有合法登录态
2. 当前是否允许发起 ingest
3. 当前失败应如何稳定暴露给用户

目标行为应是：

1. 缺少 auth 时，不进入真实 ingest 主流程
2. 错误尽可能在入口暴露，而不是在中途失败

---

## 6. 目标链路时序

任务完成后的理想链路如下：

### 6.1 Launchpad / Workspace

1. 用户在 `Electron` 中点击 `Browse Folder`
2. `Client Main Process` 打开目录选择器
3. `Client Main Process` 扫描目录内视频文件
4. `Preload` 向 `Renderer` 返回结构化文件列表
5. `Renderer` 把文件列表标准化为 `files[path]`
6. `Renderer` 调 `create_project`
7. `Renderer` 再调 `assets:import`

### 6.2 Core

1. 校验项目存在
2. 校验 `MediaReference.files[*].path` 全部合法
3. 校验当前登录态可用于云端向量化
4. 写入 `pending assets`
5. 后台执行 ingest task
6. `segmenting`
7. `vectorizing`
8. `ready` / `failed`

### 6.3 Server

1. 校验 Bearer token
2. 校验 `VectorizeRequest`
3. 调 `DashScope MultiModalEmbedding`
4. 写入 `DashVector`
5. 返回插入结果

### 6.4 Retrieval readiness

只有在以下条件全部成立时，`retrieval_ready` 才能为 `true`：

1. 至少存在一个真实 `clip`
2. 至少存在一个真实 `indexed clip`
3. 相应 `asset` 已经处于 `ready`

---

## 7. 需要删除或收敛的 fake / mock / 残留机制

本任务最重要的工程纪律不是“新增更多逻辑”，而是**删掉错误事实源**。

### 7.1 必须删除的 fake 行为

1. `create_project(payload.media)` 时自动 `_build_clips`
2. `create_project(payload.media)` 时自动 `_mark_assets_ready`
3. 任何仅凭 UI 输入媒体就直接得到 `retrieval_ready=true` 的路径

### 7.2 必须收敛的兼容行为

1. `folder_path` 如果保留，必须先扫描再展开成 `files[]`
2. Launchpad 与 Workspace 的导入行为必须统一到同一条 ingest 主链
3. Browser `File[]` 只能是调试或降级模式，不能再定义主契约

### 7.3 不允许继续存在的系统状态

1. “项目刚创建就已经有 clips”
2. “素材未索引但 UI 显示 ready”
3. “目录路径被当作视频文件路径”
4. “未登录也能开始 ingest，最后在 vectorize 阶段炸掉”

---

## 8. 任务工作流拆分

下面不是具体 patch 步骤，而是工程交付必须覆盖的工作流拆分。

### Workstream A：入口统一

目标：

1. `Launchpad`
2. `Workspace`

都必须走同一条真实 ingest 主链。

职责：

1. 去掉 `Launchpad` 带媒体创建项目时的 fake draft 注入路径
2. 统一“先建空项目，再导入素材”的交互与状态语义
3. 保证 `Workspace` 与 `Launchpad` 对导入任务的展示一致

### Workstream B：Electron 文件系统桥接

目标：

让 Desktop 端返回“目录内视频文件列表”，而不是仅返回目录字符串。

职责：

1. `Main Process` 负责目录扫描
2. `Preload` 暴露稳定最小 IPC 接口
3. `Renderer` 不直接承担目录扫描职责

设计原则：

1. 文件系统能力必须留在 `Main Process`
2. `Renderer` 只消费已结构化的数据
3. 扫描逻辑必须显式定义支持的视频扩展名

### Workstream C：Core 契约收紧

目标：

让 `core ingest` 只接受能被本地 Python 真实读取的媒体文件引用。

职责：

1. 收紧 `MediaReference`
2. 明确 `folder_path` 的语义
3. 对非法路径、目录路径、空路径做稳定错误表达
4. 在入口前置 auth gating

### Workstream D：事实状态收敛

目标：

让 `EditDraft / media_summary / capabilities` 只由真实 ingest 派生。

职责：

1. 删掉 fake clips 对状态层的污染
2. 确保 `retrieval_ready` 只依赖真实 `indexed_clip_count`
3. 确保 `active_tasks / asset.updated / edit_draft.updated` 的时序与事实一致

### Workstream E：端到端验证

目标：

构建真正能证明“真实数据已进入可检索状态”的验证闭环。

职责：

1. Electron 入口验证
2. Core ingest 验证
3. Server vectorize 验证
4. Retrieval readiness 验证
5. Agent retrieve 调用真实召回结果验证

---

## 9. 验收标准

本任务完成后，至少必须满足以下验收标准。

### 9.1 创建与导入

1. 带媒体创建项目时，项目初始 `edit_draft.assets == []` 或仅含 `pending assets`，绝不能直接出现 fake clips
2. `Launchpad` 和 `Workspace` 导入后都走 `assets:import`
3. Electron `Browse Folder` 返回的必须是目录内真实视频文件列表

### 9.2 状态流转

1. `asset.processing_stage` 必须真实经历：
   - `pending`
   - `segmenting`
   - `vectorizing`
   - `ready/failed`
2. `ready` 前不得出现 `indexed_clip_count > 0` 的伪状态
3. `retrieval_ready` 只能在真实索引成功后变为 `true`

### 9.3 错误语义

1. 未登录时，导入请求在入口被稳定拒绝
2. 目录内没有视频文件时，错误语义明确可枚举
3. 某个文件路径不存在、不可读、不是视频文件时，错误能精确定位到文件

### 9.4 事实真实性

1. `clips` 全部来自真实 ingest
2. `DashVector` 中存在对应 `clip_id/project_id/asset_id` 的真实记录
3. `retrieve` 返回的候选来自真实写入，而不是本地 fake 数据

### 9.5 agent 准入

1. ingest 完成前，`can_retrieve == false`
2. ingest 完成且索引成功后，`can_retrieve == true`
3. `agent` 的 `retrieve/inspect` 阶段只能读取真实候选池

---

## 10. 推荐测试面

本任务必须配套以下几类测试。

### 10.1 Client / Electron

1. 目录扫描单元测试
2. `preload` 暴露接口契约测试
3. Launchpad 与 Workspace 导入入口一致性测试

### 10.2 Core

1. `MediaReference` 校验测试
2. auth gating 测试
3. “目录输入非法、文件路径合法” 分支测试
4. `create_project` 不再生成 fake clips 的回归测试
5. `queue_assets_import -> _run_assets_import` 真实状态流转测试

### 10.3 Server

1. `vectorize` 契约测试
2. `DashVector` 写入错误语义测试
3. `retrieval` 读取真实插入数据测试

### 10.4 端到端

1. Electron 选目录
2. Client 展开 `files[path]`
3. Core ingest 成功
4. Server vectorize 成功
5. `retrieval_ready == true`
6. 后续 `retrieve` 得到真实候选

---

## 11. 风险与缓解

### 11.1 目录扫描结果与用户预期不一致

风险：

1. 子目录递归策略不明确
2. 非视频文件混入
3. 隐藏文件、临时文件被误扫入

缓解：

1. 明确扫描策略
2. 明确视频扩展名白名单
3. 明确是否递归子目录

### 11.2 fake 逻辑删除后，旧 UI 假设失效

风险：

1. 某些页面默认假设“带媒体创建项目后立即有 clips”
2. 删除 fake 后 UI 空态暴露出来

缓解：

1. 提前把空态视为合法状态
2. 所有页面基于事实阶段渲染，而不是基于“已有 clips”的乐观假设

### 11.3 auth gating 前置后，用户体验更严格

风险：

1. 以前未登录时还能先看到 `segmenting`
2. 现在会更早失败

缓解：

1. 明确这不是能力退化，而是错误边界前移
2. UI 给出清晰登录提示和阻塞原因

### 11.4 Desktop / Web 语义继续缠绕

风险：

1. 调试便利性再次侵入生产契约

缓解：

1. 明确“Desktop 主契约”和“Web 调试契约”是两套语义
2. 生产逻辑一律以 Desktop 本地路径模型为准

---

## 12. 本任务的最终产物

任务完成后，仓库中应该呈现出以下结果：

1. 不再存在“带媒体创建项目即伪造 ready clips”的主路径
2. `Browse Folder` 真正变成“扫描目录内视频文件并导入”
3. `Client -> Core` 的媒体导入契约收敛为真实 `files[path]`
4. `Core` 只基于真实视频文件路径做切分与抽帧
5. `Server` 只接收真实 contact sheet 图像并写入真实向量
6. `retrieval_ready` 只由真实索引成功派生
7. 后续 `agent retrieve/inspect` 只消费真实召回结果

一句话：

`EntroCut` 从“看起来像有素材理解能力”，升级为“真正以本地原视频路径为事实源完成视频理解与检索准备”。`
