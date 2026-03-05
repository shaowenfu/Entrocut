# EntroCut UI 设计白皮书（Launchpad + Workspace, MVP）

版本：`v4.1`  
适用范围：`client/`  
对应实现：`client/src/pages/LaunchpadPage.tsx`、`client/src/pages/WorkspacePage.tsx`

## 1. 设计总纲（First Principles）

### 1.1 双场景闭环（Launchpad -> Workspace）

1. `Launchpad（启动台）` 负责“开始创作”：接收素材与意图，展示项目状态。
2. `Workspace（工作台）` 负责“推进创作”：对话驱动决策、预览与分镜可视化。
3. 两者不是两个独立产品，而是一条连续心智链路：`Start Intent -> Observe AI -> Refine`.

### 1.2 `AI-first` 但可解释（Explainable）

1. 用户不必先学习复杂 `Timeline` 操作。
2. 每次 AI 改动都要看得见：`reasoning_summary`、`ops`、分镜高亮。
3. 界面目标是“降低操作成本”，不是“堆叠按钮”。

### 1.3 视觉一致性（Aether Theme Extension）

1. 统一 `zinc-950` 深色底。
2. 卡片使用 `glass` 感边框与轻量 hover，避免工业软件的厚重块状感。
3. 统一品牌元素：渐变品牌块、细边框、低饱和文本、少量高对比强调色。

## 2. Launchpad 设计（启动台）

### 2.1 核心理念

1. `Intent Drop-Zone（混合式输入区）`：拖入素材或输入 Prompt，二者都是“启动 AI”的第一性输入。
2. `AI Status Visibility（状态透传）`：项目卡片展示 `Analyzed x clips` 与 `Last AI Edit`，让用户进工作台前就知道 AI 做了什么。
3. `Fast Re-entry（快速回流）`：点击最近项目卡片，直接进入对应 `Workspace`。

### 2.2 结构分区

1. 顶栏：品牌、全局搜索占位、用户入口。
2. 左区 `Intent Zone`：
   1. 拖拽框（支持 hover 态）
   2. Prompt 输入框与创建按钮
   3. 快捷入口（`Empty Sequence`、`Connect Drive`）
3. 右区 `Recent Workspaces`：
   1. 项目缩略卡
   2. 存储状态（`Cloud Synced` / `Local Draft`）
   3. AI 状态与上次 AI 编辑说明

### 2.3 当前实现边界（MVP）

1. 只实现 UI 与页面切换，不接真实后端。
2. mock 数据集中在 `client/src/mocks/launchpad.ts`。
3. 已预留 `TODO(api)`：
   1. `POST /api/v1/projects`
   2. `POST /api/v1/projects/import`
   3. `GET /api/v1/projects`

## 3. Workspace 设计（工作台）

### 3.1 三栏结构

1. 左：`Media Dock（Assets / Clips）`
2. 中：`AI Copilot（Chat + Decision Card）`
3. 右：`Preview Stage + Storyboard Rail`

### 3.2 关键交互

1. 对话发送后进入 `isThinking`，禁用输入并展示渲染态。
2. AI 返回 `decision` 后展示结构化 `reasoning_summary + ops`。
3. 分镜卡片支持点击定位，`patch` 有脉冲高亮。
4. 导出时触发 `Edit Lock`（禁止并行编辑）。

### 3.3 设计边界

1. 不做复杂 `Timeline` 编辑器能力（拖拽剪切、关键帧、Undo）。
2. 工作台定位为 AI 决策可视化容器，不是完整 NLE 替代品。

## 4. 统一视觉 Token（摘要）

1. `bg.base`: `#09090B`
2. `bg.panel`: `rgba(255,255,255,0.02~0.06)`
3. `line.subtle`: `rgba(255,255,255,0.08)`
4. `accent.primary`: `#6D63FF`
5. `accent.secondary`: `#4AD3F5`
6. 字体：
   1. `Sora`（品牌/标题）
   2. `IBM Plex Sans`（正文）
   3. `JetBrains Mono`（状态/时间码）

## 5. 页面路由（当前）

1. `App` 默认进入 `Launchpad`。
2. Launchpad 选中项目后进入 `Workspace`。
3. Workspace 顶栏可返回 `Launchpad`。

## 6. 后续演进建议（仅方向）

1. 先补 `Launchpad` 真实数据接线，再进入 Workspace 场景化联调。
2. 保持“功能先契约后实现”：先定 `Project Summary Contract`，再替换 mock。
