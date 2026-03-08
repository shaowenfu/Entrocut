# 从 Storyboard 展示层到 EditDraft 契约落地：我的开发日记

## 写在前面

今天这轮推进的核心，不是“多做了几个功能”，而是把系统里一个很关键的中间层重新摆正了。

之前仓库里虽然已经有了 `Launchpad -> Workspace -> import -> chat -> export -> preview` 的最小闭环，但剪辑结构这一层其实还是不稳定的。前端展示的是 `storyboard`，后端推的也是 `storyboard`，页面里很多联动还是靠近似关系在猜。它能工作，但不够稳，也不够配得上后面真正要做的局部编辑。

这次工作的目标很明确：

1. 先把文档口径统一到 `EditDraft`
2. 再把 `client` 和 `core/server.py` 的 contract 实现切过去
3. 保持当前 UI 还能跑，不做一轮大拆

---

## 一、为什么今天必须动这件事

我今天最明确的判断是：

当前系统真正缺的，不是更多花哨的 `UI`，也不是更复杂的后端能力，而是一个足够稳定的剪辑中间结构层。

如果继续把 `storyboard` 当成核心结构，会有几个问题：

1. 它更像展示卡片，不像真实可执行草案
2. `scene -> clip` 的关系不显式，页面只能靠下标近似联动
3. `clip` 和“这次草案里怎么用这个 clip”混在了一起
4. 一旦要做局部编辑、重排、替换、裁短，结构会迅速不够用

所以今天最重要的决定不是“改哪个字段”，而是确认一件事：

系统的真实剪辑事实源应该是 `EditDraft`，不是 `storyboard`。

---

## 二、我今天重新固定下来的结构层次

今天我最终把层次明确成了这 4 层：

1. `Asset`
   - 原始素材
2. `Clip`
   - 分析/检索阶段得到的候选内容单元
3. `Shot`
   - 当前草案里一次具体的素材使用，是最小可编辑语义单元
4. `Scene`
   - 若干连续 `shot` 的可选工作分组

以及总容器：

1. `EditDraft`

这里有两个判断我今天特别想强调。

### 1. `Shot` 才是最小可编辑语义单元

`clip` 是分析产物，不是编辑产物。  
真正会被用户改的是：

1. 取这个 `clip` 的哪一段
2. 放在第几个位置
3. 是否启用
4. 是否锁定

所以最小编辑单元必须是“本次草案里一次具体使用”，也就是 `shot`。

### 2. `Scene` 不是必选层

我今天不想再把 `scene` 理解成客观存在的“分镜事实”了。它只是工作分组层。

如果当前任务只是逐镜头指定，那完全可以：

1. 只有 `shots`
2. 没有 `scenes`

只有当系统和用户都开始按“这一段”去讨论和修改时，`scene` 才真的值得出现。

---

## 三、文档层我做了什么

我先新建并固定了：

1. `docs/edit_draft_schema.md`

这份文档是今天所有改动的基准线。  
我在里面明确写清了：

1. 为什么不能直接退回传统 `timeline`
2. 为什么 `shot` 是最小编辑单元
3. 为什么 `scene` 是可选层
4. 为什么 `render` 最终必须以 `shots` 为准
5. 自然语言请求应该如何落到 `clip / shot / scene`

接着我把下面这些文档里涉及剪辑细节的表述统一修正了：

1. `README.md`
2. `EntroCut_architecture.md`
3. `EntroCut_algorithm.md`
4. `docs/README.md`
5. `docs/core_api_ws_contract.md`

我刻意没有去改历史开发日记和归档文档，因为那些文件保留的是当时的判断语境，不应该被事后重写。

---

## 四、实现层我做了什么

文档固定之后，我把实现层也推进到了同一口径。

### 1. `core/server.py`

这是今天实现层最核心的变化。

我不再让它内部维护：

1. `assets`
2. `clips`
3. `storyboard`

这三套并列事实源。

改成只维护：

1. `project`
2. `edit_draft`
3. `chat_turns`
4. `active_task`

其中：

1. `WorkspaceSnapshot` 现在返回 `edit_draft`
2. `chat` 现在返回的是 `EDIT_DRAFT_PATCH` 语义
3. `WebSocket` 事件里，原先的 `storyboard.updated` 改成了 `edit_draft.updated`
4. `export` 校验的也不再是“有没有 storyboard”，而是“有没有至少一个 shot”

换句话说，`core` 现在终于在 contract 层说的是剪辑草案，而不是展示层分镜。

### 2. `client/src/services/coreClient.ts`

这里我做的是类型层对齐：

1. 新增 `CoreShot`
2. 新增 `CoreScene`
3. 新增 `CoreEditDraft`
4. `CoreWorkspaceSnapshot` 改为包含 `edit_draft`
5. `ChatRequest` 增加了可选 `target`

这一步的意义是让前端读到的事实源跟文档一致，而不是继续围着旧结构打补丁。

### 3. `client/src/store/useWorkspaceStore.ts`

这里我做的是“事实源切换 + UI 派生兼容”。

具体来说：

1. `editDraft` 进入 store，成为新的事实源
2. 当前页面还在消费的：
   - `assets`
   - `clips`
   - `storyboard`
   被改成从 `editDraft` 派生
3. `storyboard` 不再代表后端真实结构，而是 `editDraft.scenes` 的展示视图
4. `WebSocket` 事件消费也改成了 `edit_draft.updated`

这是我今天最刻意的一步：  
不为了“彻底纯粹”去一口气改掉整个页面，而是先把事实源收口，再保留现有 UI 继续跑。

### 4. `client/src/pages/WorkspacePage.tsx`

这里我只动了一件非常关键的事：

把页面里最脆弱的 `Storyboard -> Clip` 联动从“按 index 猜”改成了显式映射。

也就是：

1. `scene` 不再默认对应 `clips[index]`
2. 页面直接用 `scene.primaryClipId` 去找真实 `clip`

这个改动不大，但意义很大，因为它代表：

页面联动终于开始建立在结构化关系上，而不是近似关系上。

---

## 五、今天刻意没有做的事

今天有几件事我非常明确地没有做。

### 1. 没有重写整个 Workspace UI

虽然 `storyboard` 现在已经降级成派生视图，但我没有去大改页面结构，因为今天的目标是 contract 收口，不是做新交互。

### 2. 没有引入真正的局部编辑指令流

`ChatRequest.target` 我今天只是把入口留出来了，还没有让页面真的开始发送 scene 级别或 shot 级别目标。

这是下一阶段的事。

### 3. 没有做真实渲染执行层

现在 `render` 仍然是 `in-memory` 假实现。  
但今天我已经把“渲染最终应该吃什么结构”固定住了：吃 `shots`，而不是吃 `storyboard`。

---

## 六、今天我确认下来的工程原则

今天这轮落地让我更确定几件事：

1. 剪辑系统不能把展示层对象误当成执行层对象
2. `schema` 设计必须围绕“用户最终改什么”来建，而不是围绕“UI 当前展示什么”
3. `scene` 这种高层结构必须克制，不能把创作模板预埋进底层契约
4. 当前阶段最正确的做法不是做出一个传统 `timeline`，而是先把 `EditDraft` 这个中间层做实

---

## 七、我认为下一步最值得做什么

今天把 contract 和事实源对齐之后，下一步最值得做的事情已经更清楚了。

我认为接下来最应该推进的是：

1. 把 `selected_scene_id / selected_shot_id` 真正接入前端交互
2. 让用户对某个局部目标发起 `chat`
3. 把 `edit_draft patch` 做成真正的局部修改，而不是每次整条重生成
4. 逐步减少页面对派生 `storyboard` 视图的依赖

如果这些都做对了，系统就会真正从：

1. “能生成一个结果”

走向：

2. “能对结果进行结构化、局部、可解释的修改”

这两者的差别，就是工具是否真正开始具备颠覆传统剪辑软件的潜力。
