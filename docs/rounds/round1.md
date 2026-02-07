# Round 1 开发计划（并行开发版）

## 1. Round 1 总目标

第一轮只做一件事：跑通 `End-to-End（端到端）` 主链路，形成可演示闭环。

目标链路：

1. 打开 `Desktop App（桌面应用）`
2. 上传本地视频
3. `Scene Detection（镜头切分）`
4. `Frame Extraction（抽帧）`
5. 调用 `Mock Analyze API（占位分析接口）`
6. 调用 `Mock EDL API（占位剪辑接口）`
7. `FFmpeg Render（本地拼接渲染）`
8. 在客户端预览 `final.mp4`

## 2. Round 1 范围与非目标

### 2.1 In Scope（本轮范围）

1. 三端最小可运行能力打通（`Client/Core/Server`）。
2. `Minimum Contract（最小契约）` 冻结并落地。
3. 单任务流程可稳定执行并可追踪日志。
4. 成功路径与失败路径都可回归验证。

### 2.2 Out of Scope（本轮非目标）

1. 真实 `DashScope（模型服务）` / `DashVector（向量数据库）` 接入。
2. 完整 `Auth（认证）`、多租户隔离。
3. 多任务并发调度、断点续跑。
4. 高精度算法效果优化与性能优化。

## 3. 三端并行目标（互不影响）

## 3.1 Core 端目标

1. 实现 `Core Orchestrator（核心编排器）`，驱动统一状态机。
2. 打通本地真实 `Scene Detection（镜头切分）`。
3. 打通本地真实 `Frame Extraction（抽帧）`。
4. 调用服务端 `Mock Analyze API` 与 `Mock EDL API`。
5. 按 `EDL（剪辑决策列表）` 执行 `FFmpeg Render（渲染）` 生成 `final.mp4`。
6. 向客户端持续上报：`job_state`、`running_phase`、`progress`、`error`。

Core 交付物：

1. 可执行任务入口（`START_JOB/RETRY_JOB/CANCEL_JOB`）
2. 统一任务上下文（含 `job_id` 与中间产物路径）
3. 结构化日志（可按 `job_id` 追踪）

Core 完成标准（DoD）：

1. 单个样例视频可稳定输出 `final.mp4`
2. 任一步失败可返回可枚举错误码
3. 可重复运行，重试创建新 `job_id`

## 3.2 Client 端目标（并行）

1. 实现最小工作流界面：上传、开始、进度、结果、失败重试。
2. 展示统一状态机信息，不自定义状态语义。
3. 展示关键中间结果（场景数、抽帧数量）与最终视频预览。
4. 落地本地状态镜像（`SQLite（本地数据库）`），用于恢复与回看。

Client 交付物：

1. `Workflow UI（流程界面）`
2. 错误展示面板（按 `error.type + error.code`）
3. 结果预览面板（`final.mp4`）

Client 完成标准（DoD）：

1. 无命令行参与即可完成整链路操作
2. 失败时可重试并看到可读错误信息
3. 可实时看到阶段进度变化

## 3.3 Server 端目标（并行）

1. 提供 `GET /health`。
2. 提供 `POST /api/v1/mock/analyze`（固定输入固定输出）。
3. 提供 `POST /api/v1/mock/edl`（固定输入固定输出）。
4. 返回统一错误结构，支持 `request_id` 追踪。
5. 可部署到阿里云 `ECS（云服务器）` 并公网可达。

Server 交付物：

1. `Mock API` 服务
2. 错误码与响应结构说明
3. 部署脚本/部署步骤（`ECS`）

Server 完成标准（DoD）：

1. `curl` 可验证三条接口可用
2. 错误响应结构统一
3. 服务重启可自恢复

## 4. Interface Freeze（接口冻结点）

第一轮只冻结最小必要字段，禁止在联调中反复改名。

## 4.1 全局状态机冻结

`job_state` 仅允许：

1. `IDLE`
2. `RUNNING`
3. `SUCCEEDED`
4. `FAILED`

`running_phase` 仅允许：

1. `VALIDATING_INPUT`
2. `DETECTING_SCENES`
3. `EXTRACTING_FRAMES`
4. `ANALYZING_MOCK`
5. `GENERATING_EDL`
6. `RENDERING_OUTPUT`
7. `FINALIZING_RESULT`

## 4.2 Core -> Server 契约冻结（Minimum Contract）

`POST /api/v1/mock/analyze` 请求最小字段：

1. `job_id`
2. `contract_version`
3. `video_path`
4. `frames[]`（至少 `timestamp`, `file_path`）

`POST /api/v1/mock/analyze` 响应最小字段：

1. `contract_version`
2. `job_id`
3. `request_id`
4. `analysis.segments[]`（至少 `start_time`, `end_time`, `tags[]`）

`POST /api/v1/mock/edl` 请求最小字段：

1. `job_id`
2. `contract_version`
3. `segments[]`
4. `rule`

`POST /api/v1/mock/edl` 响应最小字段：

1. `contract_version`
2. `job_id`
3. `request_id`
4. `edl.clips[]`（至少 `src`, `start`, `end`）
5. `edl.output_name`

通用请求头：

1. `Content-Type: application/json`
2. `X-Contract-Version: 0.1.0-mock`
3. `X-Request-ID: <uuid>`（可选，建议）

## 4.3 Core -> Client 上报冻结

上报对象最小字段：

1. `job_id`
2. `job_state`
3. `running_phase`
4. `progress`（0-100）
5. `error`（失败时）
6. `artifacts.output_video`（成功时）

## 4.4 错误语义冻结

错误分类固定：

1. `validation_error`
2. `runtime_error`
3. `external_error`

第一轮最小错误码集：

1. `VAL_VIDEO_NOT_FOUND`
2. `VAL_VIDEO_FORMAT_UNSUPPORTED`
3. `VAL_EMPTY_INPUT`
4. `VAL_MISSING_REQUIRED_FIELD`
5. `RUN_SCENE_DETECT_FAILED`
6. `RUN_FRAME_EXTRACT_FAILED`
7. `RUN_RENDER_FAILED`
8. `RUN_CANCELLED_BY_USER`
9. `EXT_MOCK_TIMEOUT`
10. `EXT_MOCK_UNAVAILABLE`
11. `EXT_MOCK_BAD_RESPONSE`

## 5. 联调检查点（Integration Checkpoints）

### CP1: Server 独立可用

1. `GET /health` 返回 200
2. 两个 `Mock API` 均可通过 `curl` 调通
3. 错误响应结构符合约定

### CP2: Core -> Server 打通

1. Core 可成功请求 `analyze` 与 `edl`
2. 请求失败时可正确分类为 `external_error`
3. 请求日志带 `job_id/request_id`

### CP3: Client -> Core 打通

1. 客户端可发起任务并接收阶段进度
2. 失败时可显示错误类别与错误码
3. 成功时可拿到输出视频路径

### CP4: End-to-End 闭环完成

1. 上传样例视频可生成 `final.mp4`
2. 客户端可播放预览
3. 成功/失败两条路径均可回归

## 6. Round 1 验收标准（Exit Criteria）

1. 三端并行开发后，主链路一次通过率达到可演示标准。
2. 所有状态与错误语义按冻结口径执行，无私有扩展冲突。
3. 任一失败都能定位到责任端（`Client/Core/Server`）。
4. 输出视频可复现，日志可追踪，文档可交接。

## 7. 风险与回退策略

1. `Mock API` 不稳定：优先回退到固定本地 `Mock Payload（占位响应包）` 保证联调继续。
2. `FFmpeg` 环境差异：统一版本并增加启动前检查。
3. 状态字段漂移：以本文件冻结定义为准，新增字段只能追加不能改语义。
4. 跨端联调延迟：严格按 `CP1 -> CP2 -> CP3 -> CP4` 顺序推进。

## 8. 协作与产出要求

1. 每端每日更新 `Done / Next / Risk` 三项。
2. 接口变更必须先更新文档再改代码。
3. Round 1 结束后输出一份 `Retro（复盘）`，记录阻塞、返工点、下一轮优化项。

---

文档标识：`round1_plan_parallel_dev`  
适用阶段：`Round 1（MVP先跑通）`
