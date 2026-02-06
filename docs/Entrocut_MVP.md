# Entrocut MVP执行文档（先跑通链路版）

## 1. 文档目的

本文件用于定义当前阶段 `MVP（最小可用产品）` 的目标、边界、任务拆解与验收标准。  
核心原则：先完成 `End-to-End（端到端）` 可运行闭环，再逐步优化细节。

## 2. 目标定义

### 2.1 产品目标（当前阶段）

完成以下完整流程：

1. 打开 `Desktop App（桌面应用）`。
2. 上传本地视频。
3. 本地执行 `Scene Detection（镜头切分）`。
4. 本地执行 `Frame Extraction（抽帧）`。
5. 调用云端 `Mock Server（占位服务）` 获取 `Analysis（结构化分析）` 与 `EDL（剪辑决策列表）`。
6. 本地执行 `FFmpeg（视频处理工具）` 视频拼接。
7. 在桌面端展示最终视频结果。

### 2.2 部署目标

`Mock Server（占位服务）` 部署到阿里云 `ECS（云服务器）`，桌面端通过公网地址访问并跑通链路。

## 3. 范围边界

### 3.1 In Scope（本期范围）

1. `Client（客户端）` 工作流界面与处理状态展示。
2. `Core Sidecar（本地算法进程）` 的真实切分、抽帧、拼接能力。
3. `Server（服务端）` 的 `Mock API（占位接口）`。
4. 阿里云 `ECS（云服务器）` 部署与可观测日志。
5. 最小 `E2E Test（端到端验证）` 验证链路成功。

### 3.2 Out of Scope（本期非目标）

1. 集成阿里云 `DashScope（模型服务）` 与 `DashVector（向量数据库）`。
2. 完整 `Auth（认证）`、权限体系、多租户隔离。
3. 复杂检索排序、模型精调、智能推荐。
4. 自动更新、安装包分发、商业化运营能力。

## 4. 关键策略（按你的要求）

### 4.1 `Mock Contract（占位契约）` 策略

不追求“开局完美契约”，采用 `Minimum Contract（最小契约）`：

1. 仅定义跑通链路必需字段。
2. 字段可扩展，但避免频繁改名。
3. 使用 `contract_version（契约版本）` 保留未来演进空间。

### 4.2 设计取舍

1. 先稳定流程，再打磨语义细节。
2. 先保证“可失败且可定位”，再追求“高精度与高性能”。
3. 先单用户可用，再做隔离与权限。

## 5. 系统最小闭环

1. `Client（客户端）` 选择视频并提交处理请求给 `Core Sidecar（本地算法进程）`。
2. `Core Sidecar（本地算法进程）` 输出 `scenes.json（镜头数据）` 与 `frames/*（关键帧文件）`。
3. `Core Sidecar（本地算法进程）` 调用阿里云 `Mock Server（占位服务）`。
4. `Mock Server（占位服务）` 返回 `analysis.json（分析结果）` 与 `edl.json（剪辑列表）`。
5. `Core Sidecar（本地算法进程）` 按 `edl.json（剪辑列表）` 调用 `FFmpeg（视频处理工具）` 输出 `final.mp4`。
6. `Client（客户端）` 展示处理结果与最终视频预览。

## 6. MVP任务拆解（无时间约束）

### T1. 统一流程与状态机

输出物：

1. `Workflow（流程图）`。
2. `Job State（任务状态）` 定义：`idle/running/succeeded/failed`。
3. 失败分层：`validation_error/runtime_error/external_error`。

验收标准：

1. 团队对“每一步谁负责”无歧义。
2. 任意失败都能在界面看到错误类别与错误信息。

### T2. `Core` 实现真实 `Scene Detection（镜头切分）`

输出物：

1. 输入本地视频路径，输出镜头列表（起止帧、起止时间、时长）。
2. 至少一个样例视频跑出非空镜头数据。

验收标准：

1. 结果可复现。
2. 异常路径可返回明确错误（文件不存在、格式不支持）。

### T3. `Core` 实现真实 `Frame Extraction（抽帧）`

输出物：

1. 按每镜头固定策略抽帧并落盘。
2. 返回每帧路径、帧序号、时间戳。

验收标准：

1. 帧文件可被直接访问。
2. 抽帧数量与策略一致。

### T4. `Server` 提供 `Mock API（占位接口）`

输出物：

1. `POST /api/v1/mock/analyze`：接收帧元数据，返回结构化分析。
2. `POST /api/v1/mock/edl`：接收分析结果，返回拼接片段列表。
3. `GET /health`：服务健康状态。

验收标准：

1. 固定输入返回固定输出（可回归）。
2. 接口有统一错误结构与状态码。

### T5. `Core` 实现 `Render（渲染）` 管线

输出物：

1. 将 `EDL（剪辑决策列表）` 转换为 `FFmpeg（视频处理工具）` 可执行命令。
2. 生成 `final.mp4` 与渲染日志。

验收标准：

1. 结果视频可播放。
2. 片段顺序、时长与 `EDL（剪辑决策列表）` 一致。

### T6. `Client` 工作流界面打通

输出物：

1. 上传入口。
2. 处理进度展示。
3. 关键帧预览与最终视频预览。

验收标准：

1. 用户无命令行操作即可完成整链路。
2. 失败时可重试并可查看错误摘要。

### T7. 阿里云 `ECS` 部署 `Mock Server`

输出物：

1. 运行方式：`Docker（容器）` 
2. `Nginx（反向代理）` 
3. Github action部署脚本与回滚步骤。

验收标准：

1. 公网可访问 `health`。
2. 服务重启后可自动恢复。

### T8. `E2E Test（端到端验证）`

输出物：

1. 一条标准验收脚本：打开应用 -> 上传样例视频 -> 等待完成 -> 预览 `final.mp4`。
2. 一条失败验收脚本：输入损坏视频或不存在路径。

验收标准：

1. 成功路径与失败路径均可稳定复现。
2. 日志中可通过 `job_id（任务编号）` 追踪全链路。

### T9. `Runbook（操作手册）`

输出物：

1. 本地启动说明。
2. 阿里云部署说明。
3. 常见故障排查说明。

验收标准：

1. 新成员按文档可独立运行系统。
2. 无口头依赖。

## 7. Minimum Contract（最小契约）草案

### 7.1 `POST /api/v1/mock/analyze`

请求最小字段：

1. `job_id`
2. `video_path`
3. `frames[]`（每项含 `timestamp` 与 `file_path`）

响应最小字段：

1. `contract_version`
2. `job_id`
3. `segments[]`（每项含 `start_time/end_time/tags[]`）

### 7.2 `POST /api/v1/mock/edl`

请求最小字段：

1. `job_id`
2. `segments[]`
3. `rule`（例如 `highlight_first`）

响应最小字段：

1. `contract_version`
2. `job_id`
3. `clips[]`（每项含 `src/start/end`）
4. `output_name`

说明：以上仅用于跑通链路，字段可扩展，不要求一次定型。

## 8. 验收口径（Definition of Done）

满足以下全部条件，视为本期 `MVP` 完成：

1. 桌面应用可启动并访问阿里云 `Mock Server`。
2. 本地视频可完成切分、抽帧、拼接。
3. 最终视频可在应用内预览。
4. 核心步骤失败时有清晰错误信息与日志。
5. 全流程文档可支持他人复现。

## 9. 后续演进（下一阶段）

1. 用真实 `DashScope（模型服务）` 替换 `Mock Analysis（占位分析）`。
2. 用真实 `DashVector（向量数据库）` 替换 `Mock Retrieval（占位检索）`。
3. 增加 `Auth（认证）` 与 `User Isolation（用户隔离）`。
4. 从 `Minimum Contract（最小契约）` 升级为 `Stable Contract（稳定契约）`。
