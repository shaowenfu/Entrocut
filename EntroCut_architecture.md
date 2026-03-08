### 一、 客户端 (Client: Electron + React + Zustand)

**定位：交互表现层与状态同步中心**

- **职责范围**：
    - **UI 渲染**：负责所有界面的绘制，通过数据驱动（Data-Driven）展示当前的素材、`EditDraft`、对话和预览。
    - **用户意图捕获**：监听用户的输入（Prompt）、拖拽文件夹，以及对 `shot / scene` 的局部选中和编辑意图。
    - **实时状态订阅**：作为 `Core` 的“监视器”，通过 **WebSocket** 实时订阅 `Core` 发出的状态更新（如：AI 正在思考、视频正在切片）。
    - **系统原生交互**：利用 Electron 唤起原生对话框，处理文件路径的获取并传递给 `Core`。
- **实现思路**：
    - 使用 **Zustand** 建立全局 Store，所有的状态更新不再请求云端，而是请求 `localhost:8000`。
    - 实现一个 **IPC 桥接层**，让 Web 页面能安全地调用 Node.js 的文件系统 API。

### 二、 本地引擎 (Core: Python FastAPI + Agent Engine)

**定位：核心大脑、数据加工厂与隐私屏障**

- **职责范围**：
    - **上下文工程 (Context Engineering)**：实时读取本地 `project.db`，将当前的工程状态、素材元数据、历史对话拼装成发送给大模型的 **Long Context Prompt**。
    - **Agent 逻辑编排**：运行逻辑循环（如 ReAct 模式）。决定下一步是去调用 `Server` 进行语义检索，还是更新本地 `EditDraft` 中的 `shot / scene` 结构，再交给执行层渲染。
    - **重型计算任务**：调用本地 FFmpeg 提取视频帧、处理音频流。
    - **向量化 (Embedding)**：将提取的视频帧通过 `Server` 中转给阿里云 API，获取向量并存入本地临时索引。
    - **本地存储管理**：管理 SQLite 数据库，持久化存储用户的项目配置。
- **实现思路**：
    - **FastAPI** 作为常驻进程，与 Client 保持 WebSocket 长连接。
    - 使用 **LangChain 或原生 Python** 编写 Agent 决策树。
    - **FFmpeg-python** 封装所有的底层音视频操作。

### 三、 云端服务器 (Server: Python FastAPI + Auth/Proxy)

**定位：安全网关、密钥保管员与用户中转站**

- **职责范围**：
    - **API 鉴权与中转 (Proxy)**：`Core` 不直接持有阿里云/OpenAI 的 API Key。`Core` 将请求发给 `Server`，`Server` 验证用户身份（Auth）后，代为调用大模型接口并返回结果。
    - **敏感数据托管**：管理用户的 DashVector 密钥、模型配额、订阅状态。
    - **语义检索中介**：接收 `Core` 发来的向量请求，代为查询云端向量数据库（DashVector），并将匹配结果返回给 `Core`。
    - **用户云端同步**：备份轻量级的项目元数据（不含视频原片），实现跨设备的项目列表查看。
- **实现思路**：
    - **JWT** 进行身份验证。
    - 使用 **HTTP 反向代理** 机制，隐藏真实的第三方 API 端点，防止用户非法刷取额度。

---

### 三端协作流程示例：用户说“帮我剪一个滑雪精彩集锦”

1. **Client**：捕获 Prompt，通过 WebSocket 发送给 `localhost:8000` (Core)。
2. **Core**：
    - 读取本地已向量化的素材索引。
    - 组装 Prompt：“当前素材有 A/B/C，用户要求滑雪集锦。请给出检索关键词。”
    - 发给 **Server** 换取大模型思考结果。
3. **Server**：验证用户权限，转发给大模型，返回“搜索关键词：skipping, jumping, snow spray”。
4. **Core**：
    - 拿到关键词，生成搜索向量。
    - 再次请求 **Server** 调用 DashVector 检索。
    - 根据返回的候选 `clip` 更新 `EditDraft`：先确定 `shot` 序列，必要时再形成 `scene` 分组。
    - 通过 WebSocket 把更新后的 `EditDraft` 或其派生视图推回 **Client**。
5. **Client**：Zustand 监听到数据变化，界面自动刷新 `shot / scene` 视图与预览状态。

---

### 为什么这样最合理？

- **性能最高**：Agent 就在数据（视频文件和本地库）旁边，不需要频繁把几百 K 的上下文在公网上递来递去。
- **成本最低**：服务器只需要处理文本请求和 API 转发，不需要存储任何视频数据，带宽压力极小。
- **安全性平衡**：把最关键的“钥匙（API Keys）”留在了云端，用户无法在本地反编译出你的商业账号信息。
