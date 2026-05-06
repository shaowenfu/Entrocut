# EntroCut Agent Chat UI 交互设计 (Breathing Step Flow)

## 核心理念：渐进式披露 (Progressive Disclosure)

为了解决 AI 视频剪辑过程中长思维链（CoT）和复杂工具调用带来的“信息过载”问题，我们引入了 **“呼吸式步骤流 (Breathing Step Flow)”** 设计模式。将冰冷的后端日志转化为用户能直观感受到的“智能副驾工作流”（Chat-to-Cut）。

### 1. 状态机驱动的折叠逻辑 (State-Driven Collapse)
每个工具调用步骤 (`AgentStep`) 内部维护一个展开状态，受“运行状态”和“用户干预”双重控制：
*   **执行中 (Loading)**：自动展开。视线自然聚焦到正在加载的面板和呼吸指示器上，增加等待耐心。
*   **执行完成 (Success)**：延时自动折叠（阅后即焚）。让用户看清结果后（约 1.2s），平滑收缩面板，释放屏幕空间。
*   **用户干预 (Manual Override)**：任何时候，用户点击步骤头部均可自由切换展开/折叠状态。
*   **终态收敛 (Finalization)**：当触达最终的 `AgentFinalMessage` 时，上方所有工具调用痕迹自然收敛为一列整齐的“历史清单”。

### 2. 视觉引导：折叠态的“微摘要” (Micro-Summary)
防止“状态黑盒”，通过动态标题透传信息价值：
*   *展开时（执行中）*："正在检索关于 'sunset' 的片段..."
*   *折叠时（已完成）*："✓ 已找到 6 段相关素材"

### 3. 富媒体工具可视化 (Interactive Artifacts)
*   **Retrieve Artifact**: 视频缩略图网格，包含匹配度（如 98% Match）和时长标签。骨架屏加载动画暗示数据检索。
*   **Inspect Artifact**: 单帧分析审查报告。使用等宽字体结构化显示 `[Camera]`, `[Subject]`, `[Flaws]` 等关键维度。
*   **Patch Artifact**: 类似 Git-diff 的等宽操作列表，明确标出时间线轨道的增删减改，绿色代表 `+` 插入，红色代表 `-` 移除。

### 4. 动效设计与层级 (Animation & Hierarchy)
*   **高度过渡 (Grid Transition)**：使用 `grid-template-rows: 0fr -> 1fr` 实现抽屉式丝滑展开与收缩。
*   **透明度渐变 (Fade In/Out)**：内容在高度展开后略微延迟淡入，提升界面高级感。
*   **历史弱化**：已折叠的历史步骤边框和文字变暗；当前正在执行的步骤保持高亮并带有 Spinner，成为视觉焦点。

## 组件树结构蓝图

```text
ChatTurnContainer (一轮完整的对话)
 ├─ UserMessage (用户发送的指令)
 ├─ AgentExecutionBlock (执行区块)
 │   ├─ AgentStep [Status: Success, Collapsed]
 │   │   └─ RetrieveArtifact (缩略图网格)
 │   ├─ AgentStep [Status: Success, Collapsed]
 │   │   └─ InspectArtifact (单帧 + 分析报告)
 │   └─ AgentStep [Status: Loading, Expanded]
 │       └─ PatchArtifact (轨道信息 + Diff)
 ├─ AgentFinalMessage (AI的总结性文字回复，气泡靠左)
 └─ PreviewAction (供用户点击播放的全局操作按钮)
```

这种设计完美兼顾了极客工具强大的“可追溯性”与消费级产品的“简洁感”。
