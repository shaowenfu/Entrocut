# Read Tool Contract

本文档定义 `read` 工具的字段级契约。

它的作用只有一个：

`把当前执行动作真正依赖的工作事实，稳定地读出来。`

---

## 1. 设计原则

`read` 不负责读“所有项目数据”，只负责读当前工作上下文。

所以它的输入必须表达：

1. 读哪个会话/项目
2. 想读哪类事实
3. 是否限定作用域

---

## 2. Request

```ts
type ReadTarget =
  | "goal"
  | "draft"
  | "selection"
  | "retrieval"
  | "execution"
  | "conversation"
  | "workspace_context";

type ReadScope = "global" | "scene" | "shot";

interface ReadToolRequest {
  project_id: string;
  session_id?: string | null;
  target: ReadTarget;
  scope?: ReadScope;
  scene_id?: string | null;
  shot_id?: string | null;
  expected_draft_version?: number | null;
}
```

---

## 3. Response

```ts
interface ReadToolResponse {
  project_id: string;
  session_id?: string | null;
  target: ReadTarget;
  scope: ReadScope;
  draft_version?: number | null;
  data: unknown;
  read_at: string;
}
```

`data` 的推荐载荷：

1. `goal`
   - 返回 `Goal State`
2. `draft`
   - 返回 `EditDraft`
3. `selection`
   - 返回 `Selection State`
4. `retrieval`
   - 返回 `Retrieval State`
5. `execution`
   - 返回 `Execution State`
6. `conversation`
   - 返回 `Conversation State`
7. `workspace_context`
   - 返回一组执行当前动作最常用的聚合上下文

---

## 4. Errors

```ts
type ReadToolErrorCode =
  | "NOT_FOUND"
  | "INVALID_TARGET"
  | "INVALID_SCOPE"
  | "STALE_STATE";

interface ReadToolError {
  code: ReadToolErrorCode;
  message: string;
  project_id?: string;
  session_id?: string | null;
}
```

---

## 5. 一句话结论

`read` 的本质不是“查数据库”，而是“按目标和作用域读取当前工作事实”。 
