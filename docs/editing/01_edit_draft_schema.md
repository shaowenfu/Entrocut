# EditDraft Schema

本文档定义当前阶段推荐采用的 `EditDraft schema（剪辑草案结构）`。

目标不是复刻传统 `timeline（时间轴）` 软件的数据结构，而是建立一个服务于：

1. `chat-driven editing（对话驱动剪辑）`
2. `retrieval + planning + patch（检索 + 规划 + 局部补丁）`
3. 可解释、可局部修改、可逐步落到底层执行

的中间结构层。

---

## 1. 设计心法

### 1.1 从第一性原理出发

视频剪辑最底层只有三件事：

1. 从素材中选什么
2. 这些内容按什么顺序出现
3. 每段内容以什么边界进入和退出

因此：

1. `clip` 不是剪辑结果，它是“可被选用的素材单元”
2. 真正的最小可编辑单元不是 `clip`，而是一次具体的“使用”
3. `scene` 不是客观实体，而是当前草案里的工作分组

### 1.2 不为了分类而分类

不能先假设视频天然分成：

1. 开场
2. 铺垫
3. 高潮
4. 收尾

这类结构在某些视频里成立，但不能进入底层契约。

底层契约必须只表达：

1. 稳定事实
2. 当前草案决策
3. 用户可修改的边界

### 1.3 允许“没有 scene”

`scene` 不是基础必选层，而是可选层。

所以系统应支持两种草案形态：

1. `draft -> shots`
2. `draft -> scenes -> shots`

如果当前任务只是做一个局部片段，或者用户在逐镜头指定，就不必强行升成 `scene`。

### 1.4 用户意图优先于预设模板

用户可能会说：

1. “第二个镜头太长”
2. “把这两个镜头合成一个段落”
3. “开头不要远景，直接上特写”
4. “只帮我剪中间这 12 秒”
5. “这个视频不是完整片子，只是一个片段”

所以结构必须能承接：

1. 局部替换
2. 局部删减
3. 重排
4. 分组与解组
5. 范围约束

---

## 2. 分层原则

推荐把剪辑草案拆成 4 层：

1. `Asset`
   - 原始素材
2. `Clip`
   - 分析/检索阶段得到的候选素材单元
3. `Shot`
   - 当前剪辑里一次具体的素材使用，是最小可编辑语义单元
4. `Scene`
   - 若干连续 `shot` 的工作分组，用于局部意图表达与批量修改

其中：

1. `clip` 回答“有什么可用素材”
2. `shot` 回答“这次草案具体用了什么”
3. `scene` 回答“这一组内容现在共同表达什么”

---

## 3. 核心对象定义

## 3.1 Asset

```ts
interface Asset {
  id: string;
  name: string;
  type: "video" | "audio";
  duration_ms: number;
  source_path?: string | null;
}
```

作用：

1. 表示原始素材
2. 作为 `clip` 的来源追溯对象

---

## 3.2 Clip

`clip` 是分析层对象，不是编辑层对象。

```ts
interface Clip {
  id: string;
  asset_id: string;

  source_start_ms: number;
  source_end_ms: number;

  visual_desc: string;
  semantic_tags: string[];

  confidence?: number | null;
  thumbnail_ref?: string | null;
}
```

约束：

1. `clip` 一旦生成，应尽量稳定
2. `clip` 可以被多个 `shot` 复用
3. `clip` 不承担“当前草案第几段”这类编辑语义

---

## 3.3 Shot

`shot` 是当前系统里最重要的对象。

它表示：这次草案里，具体使用了哪个 `clip` 的哪一段，并放在什么位置。

```ts
interface Shot {
  id: string;

  clip_id: string;

  source_in_ms: number;
  source_out_ms: number;

  order: number;
  enabled: boolean;

  label?: string | null;
  intent?: string | null;
  note?: string | null;

  locked_fields?: Array<"source_range" | "order" | "clip_id" | "enabled">;
}
```

解释：

1. `clip_id`
   - 指向素材理解层对象
2. `source_in_ms/source_out_ms`
   - 当前草案实际取用范围
3. `order`
   - 当前草案里的顺序
4. `enabled`
   - 允许软删除，而不是直接抹掉
5. `intent`
   - 可选，表示该 `shot` 在当前上下文中为什么被放在这里
6. `locked_fields`
   - 用户锁定某些属性后，`AI` 不得改动

为什么 `shot` 才是最小可编辑语义单元：

1. 用户改的是“这次怎么用”，不是素材本体
2. 同一个 `clip` 可能被裁不同范围、放到不同位置、服务不同目标

---

## 3.4 Scene

`scene` 是可选的工作分组层，不是素材客观层。

```ts
interface Scene {
  id: string;

  shot_ids: string[];
  order: number;
  enabled: boolean;

  label?: string | null;
  intent?: string | null;
  note?: string | null;

  locked_fields?: Array<"shot_ids" | "order" | "enabled" | "intent">;
}
```

`scene` 的定义非常克制：

1. 它只表达“这一组连续 `shot` 当前被当成一个局部片段来处理”
2. 它不预设叙事模板
3. 它不内置 `pacing / edit_role / story beat` 这类抽象字段

### scene 的存在条件

只有在以下情况之一成立时，才需要 `scene`：

1. 用户开始按“段”而不是按“镜头”修改
2. 系统需要对一组连续 `shot` 做整体替换/重排
3. 预览和交互已经需要比 `shot` 更高一层的编辑目标

否则可以只有 `shot list（镜头列表）`。

### scene 的划分原则

`scene` 的划分不是视觉分类，而是编辑边界划分。

它通常由以下因素共同决定：

1. 这些 `shot` 是否共同服务于一个局部意图
2. 用户是否会把这组内容当成一段来修改
3. 系统是否需要把这组内容作为一个整体执行 `patch`

所以 `scene` 边界本质上是模糊的、可修改的，不是严格客观事实。

---

## 3.5 EditDraft

`EditDraft` 是草案容器。

```ts
interface EditDraft {
  id: string;
  project_id: string;

  version: number;
  status: "draft" | "ready" | "rendering" | "failed";

  assets: Asset[];
  clips: Clip[];
  shots: Shot[];
  scenes?: Scene[] | null;

  selected_scene_id?: string | null;
  selected_shot_id?: string | null;

  created_at: string;
  updated_at: string;
}
```

说明：

1. `shots` 是必选
2. `scenes` 是可选
3. `selected_scene_id / selected_shot_id` 不是纯 UI 噪音，而是后续局部编辑上下文的一部分

---

## 4. 结构不变量

为了保证系统稳定，这套结构应满足以下不变量：

### 4.1 Clip 层

1. `source_start_ms < source_end_ms`
2. `clip.asset_id` 必须指向已有 `asset`

### 4.2 Shot 层

1. `shot.clip_id` 必须指向已有 `clip`
2. `source_in_ms >= clip.source_start_ms`
3. `source_out_ms <= clip.source_end_ms`
4. `source_in_ms < source_out_ms`
5. `order` 在当前草案内必须唯一

### 4.3 Scene 层

1. `shot_ids` 中的每个 `id` 必须存在
2. `scene.shot_ids` 应引用连续编辑顺序上的 `shot`
3. 一个 `shot` 同一时刻最多属于一个 `scene`
4. `scenes` 的 `order` 必须唯一

### 4.4 Draft 层

1. `shots` 是唯一真实编辑序列
2. 若存在 `scenes`，它只是对 `shots` 的分组视图，不能和 `shots` 顺序冲突
3. `render` 应以 `shots` 为最终执行输入，而不是直接以 `scene` 为输入

---

## 5. 为什么 render 以 shots 为准

这是关键原则。

`scene` 是工作分组，不是执行单元。真正可执行的是 `shot sequence（镜头序列）`。

所以：

1. `chat` 可以改 `scene`
2. `patch` 可以作用于 `scene`
3. 但最终 `render` 必须展开为有序 `shots`

这样可以避免：

1. 上层抽象污染执行层
2. `scene` 变化导致渲染语义不清
3. UI 分组和底层执行耦合过深

---

## 6. 用户自然语言如何落到这套结构

## 6.1 检索型请求

例如：

1. “找红色鞋子的镜头”
2. “找跳水的近景”

落点：

1. 更新候选 `clips`
2. 可能新增或替换某些 `shots`

## 6.2 排列型请求

例如：

1. “先远景，再中景，最后特写”
2. “把这两个镜头放到开头”

落点：

1. 更新 `shots.order`
2. 可能重建 `scene`

## 6.3 裁剪型请求

例如：

1. “第二个镜头短一点”
2. “这个镜头从人物转头后开始”

落点：

1. 更新目标 `shot.source_in_ms/source_out_ms`

## 6.4 局部替换型请求

例如：

1. “把第二段换成更近的镜头”
2. “这一段不要空镜，换成人物动作”

落点：

1. 如果存在 `scene`，优先作用于 `scene`
2. 否则作用于被选中的 `shot range`

## 6.5 分组型请求

例如：

1. “前两个镜头算一段”
2. “把这里拆成两段”

落点：

1. 更新 `scene.shot_ids`
2. 必要时新建/删除 `scene`

---

## 7. 为什么这套 schema 有用

如果没有这层结构，中间会出现两个坏结果：

### 7.1 只有 clip

问题：

1. 无法表达“本次草案具体怎么用这些素材”
2. 无法稳定承接局部修改
3. 无法解释某次编辑为什么发生

### 7.2 直接上 timeline

问题：

1. 会把产品拉回传统 NLE（非线性编辑）工具
2. 用户必须理解底层轨道、剪刀、吸附、波纹编辑
3. 自然语言编辑无法找到稳定中间层

所以 `EditDraft` 的价值在于：

1. 它是 `AI` 和用户共享的事实层
2. 它允许局部修改，而不是每次整条重做
3. 它能从高层意图逐步落到可执行序列

---

## 8. 当前阶段的落地建议

如果只做当前 `MVP`，建议按最小顺序推进：

### Phase 1

先落地：

1. `Asset`
2. `Clip`
3. `Shot`
4. `EditDraft`

此时可以没有 `Scene`。

### Phase 2

当用户已经开始提出“这段”“那段”“第二部分”这类请求时，再引入：

1. `Scene`
2. `selected_scene_id`
3. scene 级别 `patch`

### Phase 3

只有在确实需要更细执行能力时，再从 `shots` 展开到更底层渲染结构，例如：

1. 转场
2. 音频对齐
3. 文本层
4. 特效层

这些都不应反向污染当前 `EditDraft` 的核心定义。

---

## 9. 推荐最小版本

如果现在就要开始实现，推荐的最小核心契约如下：

```ts
interface EditDraft {
  id: string;
  project_id: string;
  version: number;
  status: "draft" | "ready" | "rendering" | "failed";

  assets: Asset[];
  clips: Clip[];
  shots: Shot[];
  scenes?: Scene[] | null;

  selected_scene_id?: string | null;
  selected_shot_id?: string | null;

  created_at: string;
  updated_at: string;
}
```

它足以支撑：

1. 最小闭环粗剪
2. 基于 `clip` 的语义检索
3. 基于 `shot` 的细粒度修改
4. 基于 `scene` 的局部意图编辑

这就是当前阶段最值得稳定下来的中间结构层。
