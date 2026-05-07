# Workspace Agent 交互 UI 深度改进计划

## 1. 背景与北极星目标

本计划基于当前 `client/src/pages/WorkspacePage.tsx`、`client/src/pages/LaunchpadPage.tsx`、`client/src/index.css`、`client/src/store/useWorkspaceStore.ts`、`client/src/store/useLaunchpadStore.ts` 与 `client/src/services/coreClient.ts` 的实际结构制定。

北极星目标：让 EntroCut 的 Agent 交互从“通用 AI 聊天框”升级为“面向视频语义剪辑的工作台”。界面需要流畅、稳定、可追溯、低认知负担，并让用户能用明确引用控制素材与片段，而不是依赖 AI 猜测。

本轮明确 Non-goals（非目标）：

- 不引入新的全局 UI framework（界面框架）。
- 不把 Debug details（调试细节）暴露给普通用户。
- 不在前端伪造后端没有持久化的数据契约。
- 不提前实现复杂的多用户协作、云端同步、权限系统。

## 2. 当前代码结构与关键问题

### 2.1 `WorkspacePage.tsx`

当前 `WorkspacePage.tsx` 承担了大量职责：

- Workspace 顶栏与项目重命名。
- 左侧 Assets/Clips 媒体区。
- 中间 Agent chat（聊天）与 composer（输入器）。
- 右侧 preview（预览播放器）与 storyboard（故事板）。
- 本地媒体源恢复、thumbnail（缩略图）生成、播放器同步、agent step（Agent 步骤）适配。

这种集中式结构短期可以继续工作，但新需求会明显增加局部复杂度，尤其是：

- Mention/Autocomplete（引用自动补全）需要解析输入、维护 token（标记）、渲染 chip（实体标签）、键盘交互。
- Clips 过滤需要根据 asset selection（素材选择）派生列表。
- Agent 工具结果点击需要继续复用现有 `handleAgentClipSelect` 和 preview selection（预览选择）逻辑。

建议本轮仍保持改动局部化，但把纯 helper（辅助函数）和小组件提炼在同文件顶部，避免一开始跨文件拆分带来迁移风险。等 UI 行为稳定后，再把 `AssetKnowledgePanel`、`ClipMasonryPanel`、`MentionComposer` 拆出去。

### 2.2 `LaunchpadPage.tsx`

当前 Launchpad（启动台）仍以 Project（项目）为中心：

- `ProjectMeta` 只有 `thumbnailClassName`，实际封面是前端渐变占位。
- `CoreProject` 只有 `id/title/summary_state/lifecycle_state/created_at/updated_at`，没有 cover（封面）字段。
- `updateProject` 只支持 `{ title }`，不支持 cover。

因此“删除 Project 文案”和“提供上传 Project 封面”分属两个层级：

- 文案与布局：纯前端即可改。
- 封面上传与持久化：需要新增 schema（数据结构）与 API contract（接口契约），否则刷新后必然丢失。

### 2.3 CSS（样式）

当前样式主要在 `client/src/index.css`，同时仍存在 `client/src/styles/workspace.css`、`launchpad.css`。实际页面入口中：

- `WorkspacePage.tsx` 主要依赖 `index.css`。
- `LaunchpadPage.tsx` 显式 import（导入）`../styles/launchpad.css`，但 `index.css` 也包含 Launchpad 样式，存在重复维护风险。

本轮计划以 `index.css` 为主做落地，后续可单独做 CSS ownership（样式归属）整理。

## 3. 总体设计方向

### 3.1 Agent chat 名称与品牌化

将中间聊天框从通用 `AI Copilot` 改为更贴合 EntroCut 的名称：

推荐名称：`Cutroom`

理由：

- 不是泛化的 Copilot（副驾驶）套路。
- 直接指向 editing room（剪辑室）语义，适合视频剪辑产品。
- 足够短，适合中列窄宽度标题。
- 可与 “EntroCut” 品牌并存，例如 tooltip（悬浮提示）中写 `EntroCut Cutroom`。

备选：

- `SceneSmith`：更偏镜头/场景锻造，风格更强，但不如 Cutroom 直观。
- `Edit Desk`：实用但偏普通。

同时删除右侧 `Session #7GVM6G3V`。该信息对用户没有实际操作价值，属于内部状态泄露。若未来需要定位问题，应进入 diagnostics（诊断）或日志，不放在主 UI。

图标使用用户提供的剪刀聊天图。建议落为静态资源：

- 新增 `client/public/entrocut-cutroom-icon.png`。
- `WorkspacePage.tsx` 中用 `<img>` 替代 `MessageSquare`。
- 通过 CSS 控制为 22x22 或 24x24，保留圆角与暗色模式描边。

### 3.2 Suggestion row（建议行）滚动条

问题：暗色模式下系统默认白色 scrollbar（滚动条）刺眼。

方案：

- 给 `.suggestion-row` 增加 `scrollbar-color` 与 `scrollbar-width`。
- 针对 WebKit scrollbar（Chrome/Electron）定制高度、thumb（滑块）、track（轨道）。
- 使用低对比度半透明色，hover 时轻微提亮。

验收标准：

- 横向滚动可见但不抢视觉焦点。
- 暗色模式下没有纯白滚动条。
- 不影响触控板横向滚动。

### 3.3 Storyboard 空状态铺满

当前 `No Storyboard Yet` 使用 `.story-end`，`min-width: 110px`，所以空状态只占一小块。

方案：

- 在 `storyboard.length === 0` 时使用专用 class，例如 `.storyboard-empty-state`。
- 让它 `flex: 1`、`width: 100%`、`min-width: 100%`，填满 storyboard rail（故事板轨道）。
- 视觉上采用完整空态面板，而不是末尾卡片：
  - 中央 icon（图标）+ “No Storyboard Yet”
  - 一句极短引导，如 “Ask Cutroom to draft a sequence.”
  - 不做大面积营销化文案。

验收标准：

- 右侧 storyboard 空状态在当前面板宽度内完整铺满。
- 有 storyboard 后仍显示普通横向 scene cards（场景卡片）和 END 卡。

### 3.4 其他小修复
- 视频播放器下方的暂停/播放按钮目前是一个三角形，建议改为更标准的播放图标（右三角）和暂停图标（双竖），以提升可识别性。

## 4. 左侧媒体区：从仓库到语义知识库

### 4.1 信息架构

左侧不再表达为“文件仓库”，而是表达为 Semantic Library（语义知识库）：

- 顶部 tabs（标签页）可保留 `Assets` / `Clips`，但视觉语义改为更偏“可引用上下文”。
- Assets 是原始素材，是用户可明确引用的一级实体。
- Clips 是从素材中切分出的语义片段，是 Agent 检索和剪辑的最小视觉单位。

### 4.2 Assets 卡片重构

当前 `asset-grid` 是双列小卡片，适合缩略图仓库，不适合语义引用。

目标布局：

- 单列 full-width card（满宽卡片），竖向排列。
- 左侧固定 96-112px 宽的 16:9 thumbnail（缩略图）。
- thumbnail 左上角显示短编号：`#A1`、`#A2`、`#A3`。
- 右侧显示：
  - 文件名。
  - duration（时长）。
  - clip count（片段数）与 indexed count（已索引数）。
  - processing state（处理状态）用紧凑 badge（徽标）表达。
- 操作按钮（重传、重试、删除/恢复）移动到右上或 hover action area（悬浮操作区），避免挤压主信息。

短编号生成规则：

- 基于 `visibleAssets` 当前顺序生成 `#A${index + 1}`。
- 编号只作为 UI reference alias（界面引用别名），不写入后端。
- 在输入 composer（输入器）发送前解析为稳定 asset id，避免因为排序变化导致 Agent 误解。

需要新增 helper：

- `buildAssetAliases(assets): Map<assetId, "#A1">`
- `getAssetAlias(assetId): string`
- `findAssetByAlias(alias): WorkspaceAssetItem | null`

### 4.3 Asset 引用 Autocomplete 与 Mention Chip

目标：用户输入 `@` 或 `#` 时，向上弹出 Autocomplete Menu（自动补全菜单），列出素材，并支持插入实体 chip。

推荐实现路线：

1. 第一阶段做 `#A1` alias（别名）补全：
   - 输入 `#` 弹出 asset list。
   - 菜单展示：`#A1`、缩略图、文件名、时长、索引状态。
   - 选择后在 textarea 文本中插入 `#A1`。
   - 发送前将 prompt text（提示文本）中的 `#A1` 附加解析说明，例如 `[#A1: asset_id=..., name=...]` 或作为 structured target（结构化目标）传给 API。

2. 第二阶段做真实 chip 渲染：
   - 原生 `textarea` 无法在文本内部渲染 chip，需要改为 contenteditable（可编辑内容）或 overlay（覆盖层）方案。
   - 为了 KISS（保持简单）与可验证性，先用 overlay：底层 textarea 负责输入，展示层将识别出的 `#A1` 高亮为 chip。
   - 如果要达到 Notion 级体验，再抽象 `MentionComposer` 组件。

3. 第三阶段扩展 `@视频3.mp4`：
   - `@` 搜索 filename（文件名）。
   - 菜单支持 fuzzy match（模糊匹配）。
   - 选中后仍插入 canonical alias（规范别名）`#A1`，避免长文件名污染 prompt。

关键契约选择：

- 短期不改后端 ChatRequest schema（聊天请求结构），仍发送文本。
- 在文本中插入可读引用片段，例如：
  - 用户可见：`把 #A1 的前 10 秒提取出来`
  - 发送给 core 前可增强为：`把 #A1 的前 10 秒提取出来\n\nReferenced assets:\n#A1 = video3.mp4 (asset_id=...)`
- 中期建议扩展 `ChatRequest`：
  - `references?: Array<{ kind: "asset" | "clip"; alias: string; id: string; label: string }>`
  - 这样 Agent 不再依赖 prompt parsing（提示解析）。

### 4.4 Clips 瀑布流/蜂巢状紧密排列

当前 clip card 展示了 parent、time range、desc、Match n/a 等开发者感很强的信息。

目标：

- 默认展示所有 clips。
- 使用 dense masonry/grid（紧密瀑布流/网格）布局，强调 thumbnail + match。
- 卡片只常驻展示：
  - thumbnail。
  - match badge（匹配度徽标），没有 confidence 时显示 `Indexed` 或弱化的 `--`，避免 `Match n/a`。
  - 简短时间码。
- 详细信息放入 hover tooltip（悬浮提示）或 expandable popover（弹出层）：
  - 原素材名。
  - 时间范围。
  - visual desc（视觉描述）。
  - semantic tags（语义标签，当前 `WorkspaceClipItem` 尚未映射，需要后续扩展）。

过滤系统：

- Clips 顶部增加 filter bar（过滤栏）：
  - `All Clips`
  - `From #A1`（当选中某个 asset 时出现）
  - `Ready only` 或 `High match` 可作为后续选项。
- 当用户在 Assets 区点击某个 asset：
  - 左侧 media tab 可保持 Assets，也可提供 inline action（内联操作）“View clips”。
  - 如果切到 Clips tab，则默认只展示该 asset 的 clips。
  - Clips tab 顶部提供 `Show all` 取消过滤。

状态新增：

- `clipAssetFilterId: string | null`
- `filteredClips = clipAssetFilterId ? clips.filter(clip.assetId === clipAssetFilterId) : clips`

交互验收：

- 从 Agent 工具结果点击 clip 后：
  - 切到 Clips tab。
  - 清除或设置 filter 以确保目标 clip 可见。
  - scroll/focus（滚动/聚焦）目标 clip。
  - 右侧播放器播放该 clip。
- 从 Asset 点击 `View clips` 后：
  - Clips 区只显示该素材片段。
  - 顶部显示 `#A1 video3.mp4` 与 `Show all`。

## 5. Composer 引用交互设计

### 5.1 最小可行版本

保留当前 `textarea`，新增 Autocomplete Menu（自动补全菜单）：

- 监听 caret（光标）前 token。
- token pattern（标记模式）：
  - `#` 或 `#A`
  - `@` + filename fragment（文件名片段）
- 菜单定位在 composer 上方，而不是遮挡输入内容。
- 键盘：
  - `ArrowUp/ArrowDown` 选择。
  - `Enter` 或 `Tab` 插入。
  - `Escape` 关闭。
- 鼠标：
  - hover 高亮。
  - click 插入。

最小 helper：

- `getMentionQuery(text, caretIndex)`
- `replaceMentionQuery(text, caretIndex, alias)`
- `buildMentionOptions(visibleAssets, aliases, thumbnailUrls)`

### 5.2 Chip 表达

由于 textarea 无法原生渲染局部 chip，第一版可用下方 selected references（已选引用）条表达：

- 用户插入 `#A1` 后，在输入框上方或下方展示一个 chip：`#A1 video3.mp4`。
- 文本中仍保留 `#A1`，可编辑、可删除。
- 发送时根据当前文本重新解析 alias，避免 chip 与文本不同步。

后续如果需要更像 Notion Mention：

- 用 `contenteditable` 实现 `MentionComposer`。
- 内部维护 token model（标记模型）而不是 plain text（纯文本）。
- 这会显著增加 selection（选区）与 IME（中文输入法）复杂度，建议作为独立任务。

## 6. Launchpad 改进

### 6.1 删除 Project 文案

目标不是删除项目概念本身，而是删除用户可见的“Project”措辞，让入口更贴合视频创作工作流。

建议替换：

- `Search projects...` -> `Search cuts...` 或 `Search workspaces...`
- `创建你的视频项目` -> `开始一条新剪辑`
- `Empty Sequence` 保留或改为 `Blank Cut`
- `Recent Workspaces` 保留比 `Recent Projects` 更贴近当前代码的 workspace 概念。
- `No projects` -> `No cuts yet`
- 代码变量可暂不改名，避免无意义 churn（改动噪音）。用户可见 copy（文案）优先。

### 6.2 上传 Project 封面

这需要契约升级。推荐按两阶段：

第一阶段：本地 cover registry（封面注册表）

- 用 Electron/local storage（本地存储）保存 `projectId -> coverObjectUrl/sourcePath` 映射。
- 只解决桌面本地体验。
- 风险：换机器/清缓存会丢失，不适合长期。

第二阶段：Core schema（核心数据结构）持久化

推荐做第二阶段，避免假功能。

契约新增：

- `CoreProject.cover_url?: string | null`
- `CoreProject.cover_asset_id?: string | null`
- `UpdateProjectRequest` 从 `{ title: string }` 改为：
  - `{ title?: string; cover_url?: string | null; cover_asset_id?: string | null }`
- 新增上传封面 API：
  - `POST /api/v1/projects/{project_id}/cover`
  - 或复用资产缩略图：只允许从已有 asset/clip 选择 frame（帧）作为 cover。

推荐产品方案：

- 首版不上传任意图片，而是“从已有素材选择封面”：
  - 更符合视频剪辑产品。
  - 不需要额外文件上传链路。
  - 可直接复用 thumbnail（缩略图）生成逻辑。
- 后续再允许本地图片上传。

Launchpad UI：

- recent card hover 时显示 cover action（封面操作）按钮。
- 支持 “Use current preview as cover”（使用当前预览作为封面）可放到 Workspace 顶栏或 preview 面板。
- 没有 cover 时使用当前渐变占位。

## 7. 实施阶段拆分

### Phase 1：低风险视觉修复

文件：

- `client/src/pages/WorkspacePage.tsx`
- `client/src/index.css`
- `client/public/entrocut-cutroom-icon.png`

任务：

- `AI Copilot` -> `Cutroom`。
- 删除 `session-badge` 渲染与 `sessionLabel` 派生。
- 替换聊天 header icon（图标）。
- 修复 `.suggestion-row` scrollbar（滚动条）。
- 为 storyboard 空状态新增 full-width empty state（满宽空态）。

验证：

- `npm run typecheck`
- `npm run build`
- 桌面宽度与窄宽度截图检查。

### Phase 2：Assets 语义知识库卡片

文件：

- `client/src/pages/WorkspacePage.tsx`
- `client/src/index.css`

任务：

- 新增 alias map（别名映射）生成。
- 将 `.asset-grid` 改为单列 `.asset-list` 或保持 class 但改 grid 为单列。
- 卡片改为 thumbnail + info 横向布局。
- 显示 `#A1` badge（编号徽标）。
- 保留处理/失败/源文件缺失状态。
- 保留删除、恢复、重试、重传操作。

验证：

- active/processing/deleted/source missing 四类状态不重叠。
- 文件名超长时 ellipsis（省略）不撑破布局。
- 左列拖拽宽度变化时卡片仍可读。

### Phase 3：Clips 密集瀑布流与过滤

文件：

- `client/src/pages/WorkspacePage.tsx`
- `client/src/index.css`

任务：

- 新增 `clipAssetFilterId` state（状态）。
- Asset 卡片增加 `View clips` 行为。
- Clips tab 顶部增加 filter bar。
- clip list 改为 dense grid（密集网格），例如 `grid-template-columns: repeat(auto-fill, minmax(74px, 1fr))`。
- Clip 常驻信息缩减为 thumbnail、match、time。
- 详情进入 `title` 或自定义 hover popover。
- `handleAgentClipSelect` 确保目标 clip 在当前过滤下可见。

验证：

- All Clips 与单 Asset clips 切换正确。
- 点击 Agent 工具结果 clip 后，左侧目标 clip 被聚焦并且右侧播放器播放。
- `score === "n/a"` 不显示为 `Match n/a`。

### Phase 4：Composer 引用 Autocomplete

文件：

- `client/src/pages/WorkspacePage.tsx`
- `client/src/index.css`

任务：

- 新增 mention query（引用查询）解析 helper。
- 新增 autocomplete menu（自动补全菜单）渲染。
- 支持 `#`、`@` 触发。
- 支持键盘与鼠标选择。
- 插入 canonical alias（规范别名）`#A1`。
- 发送前增强 prompt 或准备后续 `references` contract（引用契约）。

建议第一版发送策略：

```text
用户原文：
把 #A1 的前 10 秒提取出来

发送给 core：
把 #A1 的前 10 秒提取出来

Referenced assets:
#A1 = video3.mp4 (asset_id=...)
```

后续再把 `references` 加到 `ChatRequest` schema。

验证：

- 中文输入法 composition（组合输入）期间不误触发 Enter 发送。
- `Escape` 只关闭菜单，不清空输入。
- 菜单打开时 `Enter` 选择 mention，菜单关闭时 `Enter` 发送。
- 删除 `#A1` 后 chip/引用列表同步消失。

### Phase 5：Launchpad 封面与文案

文件：

- `client/src/pages/LaunchpadPage.tsx`
- `client/src/store/useLaunchpadStore.ts`
- `client/src/services/coreClient.ts`
- 后端 project schema/API（待具体定位）
- `client/src/index.css` 或 `client/src/styles/launchpad.css`

任务：

- 替换用户可见 `Project` 文案。
- 设计 `Project cover` 契约。
- 更新 `CoreProject`、`ProjectMeta`、`mapProjectMeta`。
- recent card 支持 cover image（封面图）优先，fallback（兜底）使用渐变。
- 增加 cover action（封面操作）入口。

推荐先做“从已有素材/当前预览设为封面”，暂不做任意图片上传，降低文件上传链路复杂度。

验证：

- listProjects（项目列表）返回 cover 后 Launchpad 正确展示。
- cover 不存在时不破坏现有卡片。
- rename（重命名）与 cover update（封面更新）互不覆盖。

## 8. 风险与隐藏 bug 清单

1. `#A1` alias（别名）如果只基于过滤后的 `visibleAssets`，切换 deleted/active 或排序变化会导致别名变化。发送时必须解析当前文本并附带 asset id，不能让后端只看 `#A1`。
2. `textarea` 内实现 chip 是高复杂度点。第一版不要强行 contenteditable（可编辑内容），否则容易引入 IME、selection、undo stack（撤销栈）问题。
3. Clips 数量很大时，如果每个 clip 都渲染图片与复杂 hover，可能卡顿。第一版用 CSS grid + 简单 title，后续再引入 virtualization（虚拟列表）。
4. Agent clip 点击与 clip filter（片段过滤）可能冲突。点击工具结果时必须保证目标 clip 不被当前 filter 隐藏。
5. Launchpad cover 如果只存在前端本地状态，刷新会丢失。必须在文档和实现中明确这是 prototype（原型）还是持久功能。
6. 当前 CSS 存在 `index.css` 与 `styles/*.css` 双重样式来源，改动时要防止同名 selector（选择器）互相覆盖。

## 9. 测试与验收清单

基础验证：

- `npm run typecheck`
- `npm run build`
- `git diff --check`

交互验证：

- 无素材、处理中、处理失败、源文件缺失、已删除素材都能正常显示。
- 选中 Asset 后，Preview（预览）播放原素材。
- 从 Asset 查看 Clips 后，只展示该素材 clips；点击 Show all 恢复全部。
- 点击 Clip 后，Preview 播放该 clip，并从 clip start（片段起点）开始。
- Agent 工具结果中的 clip 点击后，左侧 clip 聚焦、右侧播放器播放。
- Suggestion row 在暗色模式下滚动条不刺眼。
- Storyboard 空状态铺满右侧宽度。
- Launchpad 无 cover、有 cover、重命名中三种状态布局不重叠。

视觉验收：

- 左侧媒体区信息密度提升，但不出现 Debug backend（调试后台）观感。
- 中间聊天区命名、图标与 EntroCut 品牌一致。
- 右侧空 storyboard 不再像一个小尾卡，而是明确的工作区空态。

## 10. 推荐落地顺序

优先顺序：

1. Phase 1：立即修复视觉噪点，风险最低。
2. Phase 2 + Phase 3：把左侧媒体区改造成 Semantic Library（语义知识库）。
3. Phase 4：在稳定媒体结构上实现引用输入。
4. Phase 5：处理 Launchpad 封面，需要先定后端契约。

这样可以避免把 Mention（引用）系统建立在旧 Assets/Clips 结构上，也避免先做封面上传导致 API 变更阻塞主要 Agent 体验。
