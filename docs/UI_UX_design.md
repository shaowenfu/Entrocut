EntroCut - UI/UX 设计规范说明书

## 1. 设计概述 (Design Overview)

EntroCut 是一款面向未来的 AI 驱动非线性编辑（NLE）应用。其设计核心理念是 "熵减" (Entropy Reduction) —— 通过 AI 消除繁琐的操作步骤，让创意直达结果。

- 风格定位: 极简主义 (Minimalism)、专业暗色系 (Dark Pro)、沉浸式 (Immersive)。
- 核心隐喻: AI Copilot 是用户的“副驾驶”，界面设计弱化了复杂的参数面板，强化了自然语言交互。

## 2. 视觉识别系统 (Visual Identity)

### 2.1 色彩体系 (Color Palette)

采用深邃的暗色背景以减少视觉疲劳，配合高饱和度的霓虹色作为 AI 交互的视觉锚点。

**背景色 (Surface)**

- #121212 (Main Background): 主工作区背景，接近纯黑但带有温度。
- #18181b (Secondary Background): 侧边栏、顶部栏、面板背景 (Zinc-900)。
- #27272a (Borders/Dividers): 细微的分割线，保持层级感但不抢眼。

**主色调 (Primary)**

- #9333ea (Purple-600) -> #a855f7 (Purple-500): 代表 AI 智能、魔法、生成式操作。
- #2563eb (Blue-600): 代表常规操作、选中状态、确定按钮。

**功能色 (Functional)**

- 音频轨道: #14b8a6 (Teal-500) - 清新的波形显示。
- AI 生成内容: 紫色高亮或流光效果。
- 文本/图标: #e4e4e7 (Zinc-200) 为主文本，#71717a (Zinc-500) 为次级信息。

### 2.2 排版与图标 (Typography & Iconography)

- 字体: 无衬线字体 (Sans-serif)，如 Inter 或 Roboto，强调清晰易读。
- 时间码: 使用等宽字体 (Monospace)，如 JetBrains Mono，确保数字对齐。
- 图标: 采用线性图标 (Lucide React Icons)，笔触精细 (Stroke width 1.5-2px)，保持界面轻盈感。

## 3. 界面布局详解 (Layout Breakdown)

### 3.1 启动页：项目管理 (Project Hub)

用户进入应用的第一个触点，强调“快速开始”。

- 布局结构: 左侧固定导航栏 + 右侧自适应内容区。
- 核心亮点:
	- AI 速启卡片 (AI Quick Start): 位于内容区顶部的显著位置。采用渐变背景和模糊光效。用户无需新建项目再导入素材，而是直接输入“帮我剪辑一个京都旅游 Vlog”，AI 即可自动初始化项目。
	- 卡片式列表: 项目展示采用 16:9 的卡片设计，鼠标悬停时播放预览（Hover-to-Play），直观展示视频内容。

### 3.2 主工作台：编辑器 (Main Editor)

采用经典的非编布局变体：上三下一。

**A. 顶部区域 (Top Workspace - 65% Height)**

采用三栏式水平布局：

- 左侧：资源库 (Media Library)
	- 设计: 极简的 Grid 网格布局。
	- 交互: 鼠标悬停显示“+”号快速添加到时间线。去除了复杂的文件夹树，依靠强大的 语义化搜索 (例如搜索“快乐的镜头”) 来管理素材。
- 中间：监视器 (Preview Player)
	- 设计: 占据核心视觉区域。播放器边框极窄，最大化画面。
	- 控件: 悬浮式或底部沉浸式控制条，仅保留播放、跳转、时间码。
- 右侧：AI Copilot (The Brain)
	- 地位: 替代了传统 NLE 软件中复杂的“属性检查器” (Inspector)。
	- 交互:
		- Chat Interface: 类似 ChatGPT 的对话流。
		- Context Aware: 选中某个片段时，AI 会主动提供相关建议（如“为这段视频降噪”）。
		- Quick Chips: 输入框上方的快捷指令胶囊（“✨ 一键调色”, “📝 生成字幕”），降低用户思考成本。

**B. 底部区域 (Timeline - 35% Height)**

- 设计: 磁吸式轨道 (Magnetic Timeline)。
- 视觉:
	- 片段 (Clips): 圆角矩形设计，带有缩略图和波形。
	- 颜色编码: 视频(蓝色)、音频(青色)、AI生成内容(紫色)、转场(深色/透明)。
	- 播放头 (Playhead): 贯穿上下的细线，带有高亮手柄，确保精确剪辑。

## 4. 核心用户体验 (UX Patterns)

### 4.1 "Chat-to-Edit" (对话即剪辑)

- 传统模式: 用户在菜单中寻找“降噪” -> 打开面板 -> 调节参数 -> 应用。
- EntroCut 模式: 用户在右侧输入“把背景噪音去掉” -> AI 识别指令 -> 自动应用降噪滤镜 -> 反馈“已完成降噪处理”。

### 4.2 渐进式披露 (Progressive Disclosure)

界面默认隐藏高级参数（如具体的色轮、均衡器）。只有当用户通过 AI 无法满足需求，主动点击“高级设置”或向 AI 询问“我想手动调节曲线”时，详细面板才会浮现。

### 4.3 实时反馈 (Real-time Feedback)

- AI 思考状态: 当 AI 处理视频（如生成配音）时，界面会有微弱的脉冲光效或骨架屏加载动画，缓解用户等待焦虑。
- Toast 通知: 操作完成后，AI 此时会在对话框内给予确认（✅），而不是弹出一个阻断式的弹窗。