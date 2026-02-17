# EntroCut v0.1 Functional Spec（功能规格）- AI-first（AI 优先）

## 0. 目标与边界
- 目标：先完成 AI Copilot（AI 副驾驶）驱动的主流程 + 基础视频编辑器（Video Editor（视频编辑器））可视化，编辑器用于展示与修正，避免 AI 操作黑盒化。
- 核心路径：Project Hub（项目管理） -> AI Quick Start（AI 速启）/AI Copilot（AI 副驾驶） -> Timeline（时间线）可视化与少量手动调整 -> Export（导出）。
- 明确非目标（Non-goals（非目标））：
1. AI 直接修改 Timeline（时间线）或自动剪辑。
2. Semantic Search（语义检索）与自动片段推荐。
3. Cloud Sync（云端同步）与真实 Multi-User（多用户）权限实现。
4. 高级调色、特效、复杂转场。

## 1. 页面与模块

### 1.1 Project Hub（项目管理）
- 入口：应用启动后默认页面。
- 功能：
1. 新建项目（Create Project（创建项目））。
2. 最近项目列表（Recent Projects（最近项目））。
3. 搜索项目（Search（搜索））。
4. 进入项目后打开 Main Editor（主编辑器）。
- 状态：
1. Empty（空状态）：无项目。
2. Loading（加载中）：列表拉取。
3. Error（错误）：读取失败提示。

### 1.2 Main Editor（主编辑器）
模块分区遵循 UI 草图：
- Media Library（素材库）：左侧。
- Preview Player（预览播放器）：中间。
- AI Copilot（AI 副驾驶）：右侧。
- Timeline（时间线）：底部。

## 2. 模块功能与交互

### 2.1 Media Library（素材库）
- 主单位：Asset（素材）= 原始视频文件。
- 功能：
1. Import（导入）视频素材。
2. 列表/网格视图切换（List/Grid）。
3. 基础筛选（视频/音频）。
4. 拖拽素材到 Timeline（时间线）。
5. Segment View（片段视图）入口：默认关闭，仅入口存在（后续接入语义检索）。
- 状态：Empty（空）、Loading（加载）、Error（错误）。

### 2.2 Preview Player（预览播放器）
- 基础控制：Play/Pause（播放/暂停）、Scrub（拖拽定位）、Timecode（时间码）。
- 同步：与 Timeline（时间线）播放头同步。
- 非目标：AI Overlay（AI 叠加层）与高级标注。

### 2.3 Timeline（时间线）
- 目标：服务 AI-first（AI 优先）流程的可视化与必要纠偏，提供最小手动编辑能力。
- 最小操作集：
1. Drag（拖拽）Clip（剪辑片段）到时间线。
2. Move（移动）Clip 位置。
3. Trim（裁剪）Clip 起止点。
4. Split（分割）Clip。
5. Delete（删除）Clip。
- 轨道：至少 1 条视频轨（Video Track（视频轨））+ 1 条音频轨（Audio Track（音频轨））。
- 非目标：Ripple Delete（波纹删除）、多机位、自动对轨、Undo（撤销）。
- 技术策略（方向性，不做实现约束）：Timeline 需要自研组件；可先用 DOM（文档节点）+ 交互，再迭代到 Canvas（画布）或 WebGL（图形加速）。

### 2.4 AI Copilot（AI 副驾驶）
- 定位：剪辑领域的 Agent（智能体），未来通过 Tool（工具）+ Skill（技能）调用完成任意视频操作；v0.1 不实现具体操作，仅保留可扩展性。
- UI：对话输入框 + 历史消息列表 + Quick Chips（快捷指令胶囊）。
- 行为：只产出文本回应，不改动 Timeline（时间线）。
- 状态：
1. Idle（空闲）。
2. Typing（输入中）。
3. Loading（伪响应中）。
- 非目标：指令解析、工具调用与编辑器动作执行。

### 2.5 Export（导出）
- 仅提供 Single Preset（单一默认预设），不支持并行编辑。
- 入口：Main Editor（主编辑器）右上角按钮。
- 状态：Queued（排队）/ Rendering（渲染中）/ Success（成功）/ Failed（失败）。

## 3. 数据要求（UI 视角）
> 本节只定义 UI 必需数据，不定义系统契约。

- Project（项目）：id, name, createdAt, updatedAt。
- Asset（素材）：id, filePath, duration, thumbnail。
- Clip（剪辑片段）：id, assetId, start, end, trackId。
- Timeline（时间线）：tracks[]（轨道列表）。
- Chat Message（对话消息）：id, role, content, createdAt。
- Export Task（导出任务）：id, status, outputPath。

## 4. 体验规范（最小）
1. 任何操作失败需显示 Error Toast（错误提示）。
2. Timeline（时间线）不提供 Undo（撤销），需在 UI 明示。
3. 导入素材与渲染结果必须具备 Loading（加载）反馈。

## 5. Non-goals（非目标）
- Semantic Search（语义检索）
- Auto Edit（自动剪辑）
- AI 指令驱动 Timeline
- Cloud Sync（云端同步）
- Plugin System（插件系统）
 - AI Quick Start（AI 速启）落地实现

## 6. 验收口径（Definition of Done）
1. 可创建/打开项目并进入编辑器。
2. 可导入视频素材并拖入时间线。
3. 可在时间线完成拖拽、分割、删除、裁剪。
4. 可进行预览播放与导出成片。
5. AI Copilot（AI 副驾驶）对话 UI 可正常交互（不驱动编辑器）。

## 7. 预留扩展（Extensibility（可扩展性））
1. AI Copilot（AI 副驾驶）预留 Tool（工具）/Skill（技能）调用接口，但 v0.1 不实现。
2. AI Quick Start（AI 速启）仅保留入口与占位 UI，不做功能落地。
