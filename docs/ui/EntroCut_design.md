# EntroCut Workspace UI 设计与交互白皮书（MVP V3）

版本：`v3.0 (AI Storyboard Edition)`

适用范围：`client/` 工作台界面

核心愿景：打造基于“第一性原理”的 AI 优先视频创作控制室，用“意图可视化”取代“繁琐的手工拼接”。

## 1. 核心设计理念 (First Principles)

### 1.1 摒弃传统时间轴，引入「AI Storyboard（分镜流）」

传统剪辑软件底部的时间轴（Timeline）是为“精准裁剪（Authoring）”设计的，其本质是物理时间的堆叠。对于 AI 剪辑工具，用户不需要关心某段视频切在第 12 帧还是 15 帧。
**我们的解法**：用横向滑动的「分镜卡片（Storyboard Cards）」取代砖块状的轨道片段。每张卡片代表 AI 的一个**叙事意图**（如：开场建立镜头、情感高潮、动作快剪），使用户在宏观层面掌控影片节奏，建立对 AI 的信任感。

### 1.2 Copilot 居中，建立「沟通驱动」的心智

传统剪辑界面的核心是“预览+时间轴”。在 EntroCut 中，核心是“人机对话”。将 AI Copilot 面板放置在视觉中心（中栏）并允许加宽，强化了“通过指令驱动修改”的产品心智。

### 1.3 极度透明（Explainability）

任何画面的改变，必须配有清晰的 `Reasoning（推理理由）`。不论是对话流中的 AI Decision 卡片，还是 Storyboard 卡片上的文字说明，都在向用户解释“为什么这么剪”。

## 2. 全局视图架构 (Global Architecture)

采用 **“左-中-右”三栏自适应可拖拽布局（3-Column Resizable Layout）**。

```
WorkspaceShell
├── TopBar (顶部全局控制)
└── Main Content (水平三栏，带拖拽分割线)
    ├── Column 1: Left Media Dock (素材与高光切片库)
    ├── Splitter (可拖拽 ↔)
    ├── Column 2: Mid AI Copilot (核心对话与决策区)
    ├── Splitter (可拖拽 ↔)
    └── Column 3: Right Stage (预览与分镜流)
        ├── Preview Player (自适应播放器)
        └── AI Storyboard (底部横向分镜序列)
```

## 3. 视觉语言规范 (Visual Tokens)

方向名：**Cinematic Control Room（电影级控制室）**

- **色彩体系 (Color Palette)**
    - 背景基色 (`bg.base`): `#0B0C0E` (极深黑，用于全局背景和分割线)
    - 面板底色 (`bg.panel`): `#141820` (深蓝灰，用于各个功能面板)
    - 边框与分割 (`line.subtle`): `#232936`
    - 主强调色 (`accent.primary`): `#F05A28` (核心操作、高亮选中)
    - 次强调色 (`accent.secondary`): `#18C8C1` (AI 推理、机器运行状态)
    - 主文本色 (`text.primary`): `#F4F6FA`
    - 次文本色 (`text.muted`): `#9CA6BD`
- **字体排印 (Typography)**
    - 界面正文: `IBM Plex Sans` / `MiSans`
    - 时间码/代码/机器日志: `JetBrains Mono` 或任意 Monospace 等宽字体。

## 4. 核心模块详述 (Core Modules Specification)

### 4.1 顶部状态栏 (TopBar)

- **高度**: 固定 `56px`。
- **职责**: 展示项目名称、云端/Core引擎连接状态探针（绿色呼吸灯）。
- **操作**: 包含全局设置入口与 **Export（导出）** 按钮。导出时应触发全局 Edit Lock（禁止对话和修改）。

### 4.2 左栏：Media Dock (素材与高光库)

- **交互**: 支持与中栏之间的分割线拖拽调整宽度（默认 `260px`，最小 `200px`）。
- **标签切换**:
    1. **Assets (原始素材)**：网格视图展示用户上传的原始视频/音频文件，包含文件名和原始时长。
    2. **Clips (高光切片)**：**（重点）** 展示 AI 检索并切分出的有用片段。采用紧凑的垂直列表，必须包含：所属原始素材 Tag、AI 匹配度评分（Score）、时长跨度、以及 **AI 描述（如 "Clear sky, stable pan"）**。

### 4.3 中栏：AI Copilot (智能副驾交互区)

- **交互**: 支持左右两侧边缘拖拽调整宽度（默认 `420px`）。
- **信息流 (Conversation List)**:
    - **用户气泡**: 右对齐，展示用户的自然语言指令。
    - **AI 决策卡 (AI Decision Card)**: 左对齐。**禁止只回复纯文本**，必须包含醒目的 `AI DECISION` 标识，并结构化展示：`Reasoning Summary (推理摘要)` 和 `Operations (执行的具体操作，如替换了某镜头)`。
- **建议筹码 (Suggestion Chips)**: 输入框上方横向滑动的快捷提示词（如 "Generate rough cut"、"Match music beat"）。
- **输入区 (Prompt Composer)**: 支持多行的文本输入框，敲击 Enter 发送，Shift+Enter 换行。在 `isThinking` 状态下禁用。

### 4.4 右栏上：Preview Stage (自适应预览舞台)

- **容器比例**: 取消固定 16:9 限制，采用弹性自适应容器。无论是横屏(16:9)还是竖屏(9:16)项目，都在该区域居中且按比例缩放，周围留黑。
- **播放控制**: 将传统的复杂轨道分离，仅在播放器下方保留一条**纯粹的播放进度条（Scrubber）**，用于快速拖拽查看画面进度。
- **内嵌推理字幕**: AI 进行重大修改后，播放器底部可短暂悬浮展示当前的 `Reasoning Summary`，强化“所见即所改”。

### 4.5 右栏下：AI Storyboard (革命性分镜流)

- **高度**: 占据右栏底部约 `30%`（最小高度 `200px`）。
- **视觉呈现**: 一组横向滚动的卡片（Storyboard Cards）。
- **卡片内容契约**:
    - **Thumbnail**: 顶部为当前镜头的代表性画面（缩略图）+ 镜头持续时间（如 5s）。
    - **Title**: 镜头结构定位（如 "Establishing / 建立镜头", "Hero Reveal / 主角亮相"）。
    - **Intent (核心)**: AI 阐述该镜头的叙事意图（如 "Focus on subject emotion / 聚焦人物情绪"）。
- **联动交互**:
    - 点击卡片：播放器进度条瞬间定位至该分镜起始点。
    - 播放进行：当前播放的分镜卡片边框高亮（如 `#F05A28`），并带有轻微的呼吸动效。

## 5. 关键交互链路 (Key Interaction Flows)

1. **AI 思考状态 (isThinking)**
    - 当用户发送指令后，Copilot 列表底部出现加载动效，提示 "Analyzing footage and generating edit..."。
    - 同时，Preview 舞台上方覆盖一层半透明蒙版，显示 "RENDERING PIPELINE"，阻断预览播放。
    - Prompt 输入框禁用。
2. **局部微调动效 (Patch Highlight)**
    - 当 AI 完成修改并返回 `APPLY_PATCH_ONLY` 时，Storyboard 中被修改/替换的那张卡片（或新增的卡片）需执行一次时常为 `1200ms` 的“脉冲高亮（Pulse Highlight）”，引导用户视线。
3. **响应式拖拽边界 (Resize Boundary)**
    - 为防止界面崩溃，Splitter 拖拽必须设置极值：Left (200px - 400px)，Mid (300px - 600px)，Right 自动填满剩余空间且配置 `min-width`。

## 6. 数据状态模型建议 (State Model)

前端 Store 需维护以下核心状态：

```
type WorkspaceState = {
  // 拖拽布局状态
  layout: { leftWidth: number; midWidth: number };

  // AI 对话状态
  chat: {
    turns: ChatTurn[];
    isThinking: boolean;
  };

  // 素材库状态
  media: {
    activeTab: 'assets' | 'clips';
    assets: Asset[];
    clips: AiRetrievedClip[]; // 包含 AI 评分和描述
  };

  // 序列与播放状态
  playback: {
    currentTime: number;
    isPlaying: boolean;
  };

  // 分镜流状态 (取代原本的 timeline)
  storyboard: {
    scenes: StoryboardScene[]; // { id, title, intent, duration, thumb }
    activeSceneId: string | null;
  };
}
```