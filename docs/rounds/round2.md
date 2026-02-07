# Round 2 修复计划（基于 Round 1 代码审查）

## 1. 文档目标

本文件用于沉淀 `Round 1` 实际代码审查结果，并拆分 `Round 2` 三端并行修复任务。  
核心目标是修复主链路阻断点，恢复可演示的 `End-to-End（端到端）` 闭环。

## 2. Round 1 审查结论（结论先行）

当前状态：`core` 与 `client` 的本地测试/构建可通过，但三端联调闭环未达标。  
阻断原因主要有两个 `P0（阻断级）` 问题。

### 2.1 P0（阻断级）问题

1. `Client（客户端）` 调用 `Core（核心服务）` 旧路由，和当前状态机新路由不一致。  
   结果：任务启动、状态轮询、取消接口会直接失败（404/无效请求）。
2. `Server（云端服务）` 的 `Mock EDL（占位剪辑接口）` 返回假的 `src（源视频路径）`。  
   结果：`Core Renderer（渲染器）` 在渲染阶段校验源文件失败，任务终态为失败。

### 2.2 P1（高优先）问题

1. `request_tracking（请求追踪）` 未从 `POST body（请求体）` 解析 `job_id（任务标识）`。  
   结果：日志可观测性不足，排障效率低。
2. `Core` 对 `Mock EDL` 响应缺少前置契约校验。  
   结果：外部数据问题在渲染阶段才暴露，错误语义不够精准。

### 2.3 P2（优化）问题

1. 部分日志命名存在 `entrocat/entrocut` 拼写不一致。  
   结果：日志筛选与聚合成本升高。
2. `Server` 测试环境依赖未完全就绪（缺少 `pytest/httpx`）。  
   结果：`Server` 侧回归无法一键执行。

## 3. Round 2 总目标

1. 打通并稳定 `Client -> Core -> Server -> Core -> Client` 主链路。  
2. 保持 `T1 状态机（Workflow State Machine）` 与错误语义一致。  
3. 三端各自补齐关键测试，联调后形成可重复回归步骤。

## 4. 三端修复任务拆解（并行执行）

## 4.1 Core 工程师（你负责）

### 目标

将外部响应错误前置为可枚举错误，避免“渲染阶段才失败”。

### 任务清单

1. 在 `Mock Client（占位服务客户端）` 发起 `EDL` 请求时携带 `video_path（视频路径）`（向后兼容）。  
2. 在 `Job Orchestrator（任务编排器）` 增加 `EDL response（响应）` 契约校验：  
   `clips[]` 必须非空，`src/start/end` 必须存在且合法。
3. 若 `EDL` 契约不合法，统一归类为 `external_error（外部错误）` + `EXT_MOCK_BAD_RESPONSE`，并在 `GENERATING_EDL` 阶段失败，不进入渲染。
4. 维持 `fallback（回退）` 策略：仅在外部不可用/超时时触发本地回退，不吞掉格式错误。
5. 补充 `unit test（单元测试）`：  
   无效 `EDL` 响应、缺失字段、错误时间范围、错误 `src` 的分类与阶段断言。

### 交付物

1. `core` 侧修复代码与新增测试。  
2. 一条最小联调证据（成功任务与失败任务各 1 条状态流）。

### DoD（完成定义）

1. 成功链路可产出 `final.mp4`。  
2. `EDL` 无效时在 `GENERATING_EDL` 阶段失败，并返回 `EXT_MOCK_BAD_RESPONSE`。  
3. 相关 `unit test` 全通过。

## 4.2 Client 工程师

### 目标

对齐 `Core API（核心接口）` 新路由，确保 UI 真实驱动状态机。

### 任务清单

1. 将 `IPC（进程通信）` 中 `job` 相关请求改为新路由：  
   `POST /jobs/start`、`GET /jobs/{job_id}`、`POST /jobs/{job_id}/cancel`。  
2. 统一字段映射：  
   `job_state -> state`、`running_phase -> phase`、`artifacts.output_video -> output_video`。  
3. 处理 `409（已有运行中任务）` 与 `404（任务不存在）` 的 UI 反馈。  
4. 历史列表与活跃任务状态保持一致，避免“历史有任务但详情空白”。  
5. 补充 `test（测试）`：  
   至少覆盖路由调用参数、状态轮询停止条件、错误展示分支。

### 交付物

1. `client` 主流程修复代码。  
2. 对应测试与一次 UI 手工走查记录。

### DoD（完成定义）

1. 桌面端可完成：选视频 -> 启动任务 -> 看到进度 -> 查看结果/错误。  
2. 不再出现旧路由调用。  
3. `client` 测试通过。

## 4.3 Server 工程师

### 目标

保证 `Mock API` 返回可被 `Core Renderer` 直接消费的最小正确数据。

### 任务清单

1. 调整 `POST /api/v1/mock/edl` 契约（向后兼容）：支持接收 `video_path`。  
2. `Mock EDL` 生成时使用真实 `video_path` 作为 `clips[].src`，禁止返回占位假路径。  
3. 完善参数校验：`contract_version`、`segments`、`video_path`（若缺失则明确错误码）。  
4. `request_tracking` 从请求体提取 `job_id`（不影响业务处理）。  
5. 统一日志命名，修复 `entrocat/entrocut` 不一致。  
6. 补齐测试依赖并确保 `server/tests/test_mock_api.py` 可执行。  
7. 增加 `test（测试）`：  
   `edl` 返回 `src` 为真实传入路径、缺少 `video_path` 的错误分支、`request_id` 透传。

### 交付物

1. `server` 侧修复代码、测试与运行说明。  
2. 最小 `curl（命令行请求）` 验证脚本。

### DoD（完成定义）

1. `Mock EDL` 返回的 `clips[].src` 可直接被 `Core` 读取。  
2. `server` 测试可本地执行通过。  
3. 日志可按 `request_id/job_id` 定位单次请求。

## 5. Round 2 联调顺序（人工调试）

1. 启动 `Server`，先用 `curl` 验证 `health/analyze/edl`。  
2. 启动 `Core`，调用 `POST /jobs/start` 创建任务并轮询 `GET /jobs/{job_id}`。  
3. 启动 `Client`，执行完整 UI 路径并核对状态流。  
4. 分别验证两条路径：  
   成功路径（输出视频可预览）与失败路径（错误码可枚举且可定位责任端）。

## 6. 跨端冻结约束（Round 2 不再漂移）

1. `Core` 任务接口仅保留：  
   `POST /jobs/start`、`GET /jobs/{job_id}`、`GET /jobs`、`POST /jobs/{job_id}/cancel`。  
2. `Server` `EDL` 最小必要输入包含 `video_path`。  
3. 错误分类固定：`validation_error/runtime_error/external_error`。  
4. 新增字段必须“向后兼容”，禁止破坏已有最小链路。

## 7. Round 2 退出标准（Exit Criteria）

1. 同一份样例视频可稳定完成端到端，客户端展示 `SUCCEEDED` 与 `final.mp4` 预览。  
2. 人工注入异常（无效路径/非法输入）时，能返回明确错误码并定位责任端。  
3. 三端关键测试均可运行通过，形成可重复回归基线。

## 8. 联调样例与 Mock 约定（新增）

### 8.1 示例视频（固定）

1. 示例视频路径（按你提供的口径记录）：`home\sherwen\MyProjects\Entrocut\屏幕录制.mp4`。  
2. 当前开发机实际绝对路径（Linux）：`/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4`。  
3. 视频时长约定：`11s`（作为 Round 2 联调基线）。

### 8.2 Mock Contract 约定（Round 2 冻结）

1. `POST /api/v1/mock/analyze` 输入最小字段：`job_id`、`contract_version`、`video_path`、`frames[]`。  
2. `POST /api/v1/mock/edl` 输入最小字段：`job_id`、`contract_version`、`video_path`、`segments[]`、`rule`。  
3. `edl.clips[]` 输出约束：每个 `clip` 必须包含 `src`、`start`、`end`，且 `end > start`。  
4. `edl.clips[].src` 必须是 `Core` 本机可访问的视频绝对路径，默认等于请求中的 `video_path`。  
5. 当 `Mock API` 返回结构缺失或字段非法时，`Core` 必须在 `GENERATING_EDL` 阶段失败，错误归类为：  
   `external_error + EXT_MOCK_BAD_RESPONSE`。

### 8.3 Round 2 演示用 Mock 数据（建议）

1. `Analyze segments` 建议返回 3 段（覆盖 11s 主体区间）：
   `0.0-3.2`、`3.2-7.0`、`7.0-10.8`。  
2. `EDL clips` 建议返回 2-3 段，均引用 `src=/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4`。  
3. `output_name` 固定 `final.mp4`，便于客户端预览路径拼装与回归对比。
