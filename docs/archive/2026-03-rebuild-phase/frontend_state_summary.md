# Frontend State Summary

本文档汇总当前 `prototype mode（原型模式）` 下，`Launchpad（启动台）` 与 `Workspace（工作台）` 已确认需要管理的前端状态。

目标不是穷举所有 UI 细节，而是明确：

1. 哪些状态会影响系统行为
2. 哪些状态决定 UI 展示
3. 哪些状态应该成为后续 `Core API/WS contract（本地 API/事件契约）` 的输入

## 1. 识别原则

一个信息应进入状态管理，通常满足以下任一条件：

1. 会影响用户下一步能不能操作
2. 会影响界面展示
3. 会影响和 `Core` 的通信
4. 会影响错误恢复

不需要进入主状态管理的，通常是纯视觉细节，例如：

1. 按钮 `hover（悬停）`
2. 输入框 `focus（聚焦）`
3. 卡片展开动画

## 2. Launchpad 状态

`Launchpad` 的核心功能：

1. 展示最近项目
2. 检查 `Core` 是否在线
3. 选择本地文件夹或文件
4. 创建空项目
5. 用 `prompt（提示词） + 素材` 创建项目
6. 创建成功后进入 `Workspace`
7. 创建失败后提示错误

对应需要管理的状态如下。

### 2.1 数据状态

1. `recentProjects`
   最近项目列表
2. `activeWorkspaceId`
   当前激活或刚创建的项目 `id`
3. `activeWorkspaceName`
   当前激活或刚创建的项目名

### 2.2 流程状态

1. `isLoadingProjects`
   最近项目是否仍在加载
2. `isCreating`
   是否正在创建项目
3. `isImporting`
   是否正在执行启动台导入动作
4. `isThinking`
   当前原型里存在，但语义较弱；若后续不承担真实 AI 过程，可考虑删除或并入更明确的任务状态

### 2.3 系统状态

1. `systemStatus`
   建议使用：
   `connecting | ready | error`
   表示 `Core` 当前是否可用

### 2.4 错误状态

1. `lastError`
   最近一次启动台错误

## 3. Workspace 状态

`Workspace` 的核心功能：

1. 展示当前项目基础信息
2. 展示素材列表
3. 展示候选 `clips（片段）`
4. 展示 `storyboard（分镜）`
5. 展示 `chat（对话）`
6. 接收用户 chat 指令
7. 展示 AI 对项目的调整结果
8. 导入或补充素材
9. 展示素材处理过程
10. 展示 AI 思考过程
11. 导出项目
12. 管理与 `Core` 的事件连接
13. 错误展示与恢复

对应状态应拆成 5 类。

### 3.1 数据状态

这些状态描述“当前项目里有什么”。

1. `workspaceId`
   当前工作台项目 `id`
2. `workspaceName`
   当前工作台项目名
3. `currentProject`
   当前项目的概览信息
4. `assets`
   当前项目素材列表
5. `clips`
   当前项目候选片段列表
6. `storyboard`
   当前项目分镜结果
7. `chatTurns`
   当前项目对话历史
8. `exportResult`
   最近一次导出的结果

### 3.2 业务流程状态

这些状态描述“项目当前进行到哪一步”。

1. `workflowState`
   建议保留以下枚举：

   - `prompt_input_required`
     刚创建空项目，等待用户给出明确意图
   - `awaiting_media`
     当前项目没有足够素材，不能进入真实剪辑
   - `media_processing`
     正在导入或处理素材
   - `media_ready`
     素材已可用，但还没有形成稳定分镜结果
   - `chat_thinking`
     正在处理用户指令，等待 `agent（智能体）` 回复
   - `ready`
     当前结果稳定，可继续 chat、补素材、导出
   - `rendering`
     正在导出
   - `failed`
     当前业务流程失败，等待用户重试或恢复

`workflowState` 的价值是统一表达主流程，而不是依赖多个分散的 `boolean（布尔值）`。

### 3.3 任务状态

这些状态描述“后台具体在跑什么任务”。

1. `activeTaskType`
   当前原型里已有：
   `ingest | chat | render | null`
2. 后续建议升级为统一 `task state`：

   - `task.type`
     `ingest | index | chat | render`
   - `task.status`
     `queued | running | succeeded | failed | cancelled`
   - `task.progress`
     可选进度

当前原型已存在的相关派生状态：

1. `isMediaProcessing`
2. `isThinking`
3. `isExporting`
4. `mediaStatusText`

这些状态短期可继续保留，但长期建议收敛到统一任务模型，避免多个 `boolean` 冲突。

### 3.4 对话状态

`chat（对话）` 需要被视为一个受约束的任务过程，而不是普通输入框行为。

核心规则：

1. 用户发送一条消息后，必须等待 `agent` 回复完成
2. 在 `agent` 回复过程中，不能再发送下一条消息

因此应显式建模：

1. `chatState`
   建议语义：
   `idle | responding | failed`

如果不单独建 `chatState`，至少要通过以下任一方式保证语义明确：

1. `workflowState = chat_thinking`
2. `activeTask.type = chat` 且 `task.status = running`

这里的 `idle` 意思是：当前 chat 流程未运行，处于空闲、可接收下一条消息的状态。

### 3.5 连接状态

这些状态描述与 `Core` 之间的实时连接，不一定直接显示在 UI 上，但必须管理。

1. `eventStreamState`
   建议使用：
   `disconnected | connecting | connected`
2. `reconnectState`
   建议使用：
   `idle | reconnecting | max_attempts_reached`
3. `lastEventSequence`
   最近一次事件序号，用于同步和重连恢复

即使这些状态不直接显示为界面元素，也必须存在，因为它们会影响：

1. 是否能收到进度事件
2. 是否能同步项目变化
3. 是否需要重连
4. 某些操作是否应被禁止或降级

### 3.6 错误状态

1. `lastError`
   最近一次业务或系统错误

需要注意：

1. 业务失败可以推动 `workflowState -> failed`
2. 连接失败不一定等于业务失败，通常应优先体现在 `eventStreamState`

## 4. 当前最重要的约束

基于当前讨论，以下约束需要明确写进状态与契约设计中：

1. 没有素材时，不能进入真实剪辑流程
2. `media_processing` 期间，不应再次启动新的素材处理
3. `chat_thinking` 期间，用户不能继续发送下一条消息
4. `rendering` 期间，不应重复触发导出
5. 连接断开时，系统应显式进入连接恢复逻辑，而不是假装在线

## 5. 一句话总结

前端状态管理不是“把所有 `if` 放在一个文件里”，而是：

1. 定义系统当前处于什么关键状态
2. 定义这些状态如何变化
3. 让 UI 和行为都从这些状态稳定派生

对当前 EntroCut 而言，最关键的不是继续增加页面细节，而是把：

1. `workflow state（业务流程状态）`
2. `task state（任务状态）`
3. `connection state（连接状态）`
4. `error state（错误状态）`

先稳定下来，后续 `Core API/WS contract` 才有可靠边界。
