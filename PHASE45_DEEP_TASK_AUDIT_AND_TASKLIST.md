# Phase 4/5 深度待办清单与链路风险审计

## 1. 目的

这份文档用于补充 [PHASE45_ENGINEER_TASK_ASSIGNMENTS.md](/home/sherwen/MyProjects/Entrocut/PHASE45_ENGINEER_TASK_ASSIGNMENTS.md)，重点不是重复已有任务，而是基于当前骨架与设计文档重新模拟每条关键功能链路，找出容易被忽略的卡点，并把这些卡点转化为新的可执行任务。

本轮审计的唯一设计依据：

1. [EntroCut_architecture.md](/home/sherwen/MyProjects/Entrocut/EntroCut_architecture.md)
2. [EntroCut_algorithm.md](/home/sherwen/MyProjects/Entrocut/EntroCut_algorithm.md)
3. [EntroCut_launchpad_design.md](/home/sherwen/MyProjects/Entrocut/EntroCut_launchpad_design.md)
4. [EntroCut_user_senerio.md](/home/sherwen/MyProjects/Entrocut/EntroCut_user_senerio.md)

## 2. 当前基线

当前已经稳定的部分：

1. `Client -> Core -> Server` 单入口主链路已经建立。
2. `Core` 已具备 `REST + WebSocket + workflow shell + tool registry + gateway shell`。
3. `Server` 已具备 `proxy service + adapter interface + mock adapter`。
4. `Client` 已具备 `Workspace` 事件流接线骨架。
5. 一次性三端冒烟脚本已通过：

```bash
bash scripts/phase45_smoke_test.sh
```

但当前通过的是“基于 mock 的主干样板链路”，距离“稳定可迭代的 MVP”还有一批高风险缺口。

## 3. 功能链路模拟与卡点补全

## 3.1 链路 A：应用启动与身份校验

### 目标流转

1. `Client` 启动，加载本地 `auth token`。
2. `Client` 探测 `Core` 和 `Server` 健康状态。
3. `Client` 获取 `runtime capabilities`，确定当前是否支持 `WebSocket / launchpad workflow / chat workflow`。
4. 用户进入启动台。

### 已有能力

1. `HTTP health check`
2. `Core / Server runtime capabilities` 基本接口

### 容易被忽略的卡点

1. `WebSocket auth` 还没有设计完成。当前浏览器 `WebSocket` 不能直接复用 `Authorization header`，后续如果继续靠裸 `ws://`，上线时一定会出问题。
2. `Client` 还没有真正消费 `runtime capabilities`，一旦后端能力和前端假设不一致，UI 会静默失败。
3. `Token invalid / expired` 只有 `HTTP` 分支有明显表现，`WebSocket` 还没有统一鉴权失败语义。
4. `Core` 或 `Server` 部分可用时的降级策略没有定义，例如：
   1. `Core` 在线但 `Server` 离线
   2. `Server` 在线但 `Embedding provider` 限流

### 新增任务

1. [1.1 WebSocket 鉴权与会话建立协议](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.2 Runtime capability negotiation（能力协商）](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [1.3 跨传输层统一鉴权失败语义](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.2 链路 B：启动台加载项目列表

### 目标流转

1. `Client` 打开启动台。
2. `Client` 请求 `Core` 的项目列表。
3. `Core` 从本地项目库读取项目卡片数据。
4. `Client` 渲染启动台卡片。

### 已有能力

1. `GET /api/v1/projects`
2. 启动台卡片 UI

### 容易被忽略的卡点

1. 当前项目列表没有“处理中进度”投影，和设计文档中的启动台定位不完全对齐。
2. 如果项目在后台继续 ingest，启动台卡片没有事件回流，卡片状态会陈旧。
3. 本地项目元数据与未来云端轻量同步元数据的冲突规则还没定义。

### 新增任务

1. [2.1 启动台卡片状态增量刷新](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.4 本地项目元数据与云端轻量同步边界](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.3 链路 C：启动台浏览目录导入

### 目标流转

1. 用户在启动台点击 `Browse Directory`。
2. Electron 选择目录并把绝对路径交给 `Client`。
3. `Client` 调 `Core` 创建项目并开始 ingest。
4. `Core` 扫描目录、去重、切分、抽帧、向量化、索引。
5. `Client` 跳转工作台，并通过 `WebSocket` 持续看到状态。

### 已有能力

1. Electron 目录桥接
2. `Core` 项目创建和素材导入
3. `Workspace` 里有基本处理中状态

### 容易被忽略的卡点

1. 浏览器降级上传与 Electron 路径导入是两条完全不同的语义，现在只是在 UI 上揉在一起了。
2. 路径规范化、Windows 驱动器大小写、中文路径、软链接路径还没统一。
3. 大目录扫描时没有“阶段化进度模型”，只有粗颗粒提示。
4. 重复导入同一目录的幂等规则还没定义。
5. 目录里混合大量非视频文件时，没有清晰的过滤统计反馈。
6. 应用中途退出后，正在 ingest 的项目如何恢复还没定义。

### 新增任务

1. [2.2 Electron 路径导入与浏览器上传语义拆分](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [3.1 Core 资产去重、路径规范化与重扫幂等](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [3.2 Ingest 阶段化进度模型](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
4. [1.5 Core 重启后的项目恢复策略](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.4 链路 D：启动台仅输入 Prompt 创建项目

### 目标流转

1. 用户只输入 Prompt，不上传素材。
2. `Client` 创建空项目。
3. `Core` 建立聊天会话。
4. `Server` 返回“需要用户上传素材”的规划或澄清。
5. `Workspace` 显示澄清对话和下一步动作。

### 已有能力

1. 空项目创建
2. 无素材聊天会返回 `ASK_USER_CLARIFICATION`

### 容易被忽略的卡点

1. “无素材”并不只是一个文案问题，而是一个显式状态机分支，后续补素材时必须能恢复同一会话。
2. 当前 `pendingPrompt` 只保留最后一条，但没有明确对用户的可见反馈和测试覆盖。
3. `Prompt-only` 项目进入工作台后，哪些操作应禁用、哪些操作应引导上传素材，还未完全定义。

### 新增任务

1. [1.6 Prompt-only 项目状态机](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [2.3 无素材工作台的显式 UI 限制与引导](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [5.1 Prompt queue 只保留最后一条的验证矩阵](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.5 链路 E：启动台 Prompt + 素材同时创建

### 目标流转

1. 用户同时提供 Prompt 和目录/视频。
2. `Core` 创建项目并启动 ingest。
3. `Core` 先发起初步意图预热，再继续媒体处理。
4. `Workspace` 进入处理中，但聊天区仍能展示 AI 的初始化反馈。

### 已有能力

1. `pendingPrompt`
2. 素材处理完成后自动继续 `chat`

### 容易被忽略的卡点

1. 当前“预热意图”和“真正开始聊天规划”还是同一路由，后续很容易把初始化意图和正式剪辑决策混在一起。
2. `pendingPrompt` 只存在 `Client store`，如果页面刷新或 `Core` 重启会丢失。
3. 媒体尚未处理完成时，AI 允许说什么、不允许做什么，边界还不够严。

### 新增任务

1. [1.7 Launchpad warmup 与 Workspace chat 的语义分层](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.8 pendingPrompt 持久化与恢复策略](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.6 链路 F：工作台 Chat-to-Cut

### 目标流转

1. 用户在工作台输入 Prompt。
2. `Client` 发送到 `Core`。
3. `Core` 做上下文工程，决定是否调用检索、向量查询、LLM 规划。
4. `Server` 返回规划结果。
5. `Core` 产出 patch 和状态事件。
6. `Client` 更新对话和分镜。

### 已有能力

1. `chat` HTTP 路由
2. `workspace.chat.*` 与 `workspace.patch.ready` 事件

### 容易被忽略的卡点

1. 当前 `HTTP response` 和 `WebSocket patch event` 都可能写同一份 assistant turn，已经做了局部规避，但还没有彻底的事件去重与顺序约束。
2. 缺少 `event sequence / revision number`，后续一旦 `reconnect` 或多事件并发，很容易乱序。
3. `Core` 的上下文工程还没有真正存在，后续若直接堆实现，会污染 `server` 与 `client`。
4. 搜索结果、规划结果、patch 应该是三个不同层次的数据，现在还比较混。

### 新增任务

1. [1.9 Event sequence 与幂等去重机制](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.10 Core Context Engineering shell](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [4.1 Server 规划结果的结构稳定性](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.7 链路 G：工作台补充上传素材

### 目标流转

1. 用户已进入工作台。
2. 在 `Assets` 区域继续上传目录或视频。
3. `Core` 新增资产、增量 ingest、增量索引。
4. `Client` 看到新增素材和阶段化进度。

### 已有能力

1. 工作台 `asset upload entry`
2. `coreImportAssets/coreUploadAssets`

### 容易被忽略的卡点

1. 增量上传后是“全量重新 ingest”还是“只处理新增资产”，当前没有冻结。
2. 当前 ingest 逻辑更接近全量重跑，后续会带来性能问题和重复事件问题。
3. 用户在 ingest 中再次上传素材时的并发规则没有定义。

### 新增任务

1. [3.3 增量 ingest 与全量重跑的策略切分](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.11 同项目多任务并发门控](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.8 链路 H：手动精修、Seek、排序调整

### 目标流转

1. 用户点击分镜进行 `seek`
2. 用户拖拽调整顺序
3. `Client` 发送局部编辑指令给 `Core`
4. `Core` 更新项目契约并回推 patch

### 已有能力

1. UI 上已有 `seek` 和只读分镜交互影子

### 容易被忽略的卡点

1. 当前 `seek` 还是纯前端局部时间指针，没有真实 `Core` 命令。
2. 排序编辑的“谁是单一真实源”还没定，未来若同时支持 AI patch 和人工拖拽，冲突会很高。
3. “编辑锁”目前是 UI 假锁，不是 `Core` 侧真正的工作流锁。

### 新增任务

1. [2.4 Client 手动编辑命令面](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [3.4 Core 项目 patch 与人工编辑合并策略](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [1.12 编辑锁与工作流锁统一](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.9 链路 I：渲染与导出

### 目标流转

1. 用户点击 `Export`
2. `Core` 锁定项目并生成预览或成片
3. `Client` 展示阶段化进度
4. 导出完成后返回文件路径并解锁编辑

### 已有能力

1. UI 上有 `Export`
2. `Core` 里有 `render` 占位

### 容易被忽略的卡点

1. 当前 `Export` 仍是纯前端假逻辑，没有 `Core` 侧状态。
2. 预览流 URL、本地成片输出目录、系统保存对话框三者的职责边界还未冻结。
3. 导出取消、失败重试、导出期间禁止编辑都还只是视觉态。

### 新增任务

1. [3.5 Render Preview 与 Export Output 分离](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [2.5 导出状态与系统保存动作接线](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [5.2 Render/Export 失败与重试验证](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 3.10 链路 J：异常、重连与恢复

### 目标流转

1. `Core` / `Server` 网络波动或进程重启
2. `Client` 感知到断线
3. 自动重连并恢复项目状态
4. 不产生重复 patch、不丢失关键状态

### 已有能力

1. 基本 health check

### 容易被忽略的卡点

1. `WebSocket reconnect` 还没实现。
2. 断线后缺少 `resync` 机制。
3. `Redis queue` 不可用时现在主要是错误返回，没有 graceful degradation（优雅降级）策略。
4. `Core/Server` 重启后，客户端当前项目态如何恢复还没定。

### 新增任务

1. [2.6 WebSocket reconnect 与 resync](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
2. [1.13 Queue 不可用的降级策略](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)
3. [5.3 断线恢复测试矩阵](/home/sherwen/MyProjects/Entrocut/PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md)

## 4. 补充后的任务总表

## 4.1 主工程师任务

| ID | 任务 | 说明 | 优先级 |
| --- | --- | --- | --- |
| 1.1 | WebSocket 鉴权与会话建立协议 | 解决 `WebSocket` 不能直接复用 `Authorization header` 的根问题 | P0 |
| 1.2 | Runtime capability negotiation | `Client` 根据 `Core/Server` 能力做显式决策，而不是写死假设 | P0 |
| 1.3 | 跨传输层统一鉴权失败语义 | `HTTP / WebSocket` 统一 `AUTH` 错误表达 | P0 |
| 1.4 | 本地项目元数据与云端轻量同步边界 | 冻结本地与云端元数据的冲突规则 | P1 |
| 1.5 | Core 重启后的项目恢复策略 | 定义恢复路径和最小恢复数据 | P1 |
| 1.6 | Prompt-only 项目状态机 | 冻结无素材项目的状态流转 | P0 |
| 1.7 | Launchpad warmup 与 Workspace chat 的语义分层 | 把初始化意图预热和正式剪辑会话分开 | P1 |
| 1.8 | pendingPrompt 持久化与恢复策略 | 避免刷新和重启丢失待执行意图 | P1 |
| 1.9 | Event sequence 与幂等去重机制 | 解决 `HTTP response` 与 `WebSocket event` 的双写与乱序 | P0 |
| 1.10 | Core Context Engineering shell | 让上下文工程回到 `Core`，不漂移到 `Client` 或 `Server` | P0 |
| 1.11 | 同项目多任务并发门控 | 限制一个项目同时 ingest/chat/render 的冲突 | P0 |
| 1.12 | 编辑锁与工作流锁统一 | 把 UI 锁和后端真实锁合并 | P1 |
| 1.13 | Queue 不可用的降级策略 | 定义 `Redis` 异常时的退化行为 | P1 |

## 4.2 工程师 A 任务

| ID | 任务 | 说明 | 优先级 |
| --- | --- | --- | --- |
| 2.1 | 启动台卡片状态增量刷新 | 让启动台卡片能看到后台项目进度变化 | P1 |
| 2.2 | Electron 路径导入与浏览器上传语义拆分 | 把两条不同语义的入口彻底分开 | P0 |
| 2.3 | 无素材工作台的显式 UI 限制与引导 | 明确何时显示上传引导，何时允许聊天 | P1 |
| 2.4 | Client 手动编辑命令面 | 为 `seek/reorder` 预留明确命令接口 | P2 |
| 2.5 | 导出状态与系统保存动作接线 | 串起 UI、Electron 保存对话框和 Core 状态 | P2 |
| 2.6 | WebSocket reconnect 与 resync | 实现断线重连和重同步 | P0 |

## 4.3 工程师 B 任务

| ID | 任务 | 说明 | 优先级 |
| --- | --- | --- | --- |
| 3.1 | Core 资产去重、路径规范化与重扫幂等 | 防止重复导入和路径漂移 | P0 |
| 3.2 | Ingest 阶段化进度模型 | 扫描、切分、抽帧、向量化、索引要拆成阶段 | P0 |
| 3.3 | 增量 ingest 与全量重跑的策略切分 | 定义新增素材的处理模式 | P1 |
| 3.4 | Core 项目 patch 与人工编辑合并策略 | 后续拖拽、替换镜头时的基础规则 | P2 |
| 3.5 | Render Preview 与 Export Output 分离 | 冻结预览和最终导出的职责边界 | P1 |

## 4.4 工程师 C 任务

| ID | 任务 | 说明 | 优先级 |
| --- | --- | --- | --- |
| 4.1 | Server 规划结果的结构稳定性 | 保证 `reasoning_summary / ops / storyboard_scenes` 稳定 | P0 |
| 4.2 | Embedding adapter 真接入 | 对接真实 `Qwen3-VL-Embedding` | P1 |
| 4.3 | DashVector index/search 真接入 | 对接真实 `DashVector` 检索 | P1 |
| 4.4 | `user_id` 过滤与检索隔离 | 保证多用户逻辑隔离不可绕过 | P0 |
| 4.5 | Quota / rate limit / provider failure 语义 | 明确限流和供应商异常的返回语义 | P1 |

## 4.5 工程师 D 任务

| ID | 任务 | 说明 | 优先级 |
| --- | --- | --- | --- |
| 5.1 | Prompt queue 只保留最后一条的验证矩阵 | 覆盖用户连续输入场景 | P0 |
| 5.2 | Render/Export 失败与重试验证 | 覆盖导出异常链路 | P1 |
| 5.3 | 断线恢复测试矩阵 | 覆盖 `Core/Server/WebSocket` 抖动与恢复 | P0 |
| 5.4 | 一次性三端 smoke 扩展为 CI smoke | 持续验证主干样板链路 | P0 |
| 5.5 | 共享工作区冲突检测脚本或清单 | 降低多人在同一工作区协作的踩踏概率 | P1 |

## 5. 结论

当前最容易被忽略、但又最可能在后续引爆返工的点有四个：

1. `WebSocket auth + session + reconnect`
2. `HTTP/WS 双通道的事件去重与顺序语义`
3. `Prompt-only / Prompt+Media / 增量上传` 三类状态机分支
4. `同一 git 工作区` 下多人协作的边界和冲突控制

这四类问题如果不提前冻结，后面的真实算法接入会持续返工。

