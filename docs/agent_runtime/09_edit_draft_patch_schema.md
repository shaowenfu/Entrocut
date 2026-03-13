# EditDraft Patch Schema

本文档定义 `patch` 工具的字段级契约。

它的作用是：

`把一次编辑决策，稳定地写成对 EditDraft 的增量修改。`

---

## 1. 设计原则

`patch` 不重写整份草案，只表达最小修改。

所以它必须满足：

1. 目标对象明确
2. 操作类型明确
3. 参数最小
4. 可验证是否成功应用

---

## 2. Operations

```ts
type EditDraftPatchOpType =
  | "insert_shot"
  | "remove_shot"
  | "replace_shot"
  | "trim_shot"
  | "move_shot"
  | "group_scene"
  | "ungroup_scene"
  | "lock_fields";
```

---

## 3. Patch Object

```ts
interface EditDraftPatchOperation {
  op_id: string;
  type: EditDraftPatchOpType;
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  after_shot_id?: string | null;
  clip_id?: string | null;
  source_in_ms?: number | null;
  source_out_ms?: number | null;
  shot_ids?: string[];
  locked_fields?: string[];
  summary: string;
}

interface EditDraftPatch {
  project_id: string;
  draft_id: string;
  base_version: number;
  scope: "global" | "scene" | "shot";
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  operations: EditDraftPatchOperation[];
  created_at: string;
}
```

---

## 4. Response

```ts
interface EditDraftPatchResponse {
  applied: boolean;
  project_id: string;
  draft_id: string;
  previous_version: number;
  next_version?: number | null;
  applied_operation_ids: string[];
  skipped_operation_ids: string[];
  updated_edit_draft?: unknown;
  responded_at: string;
}
```

`updated_edit_draft` 在当前阶段推荐直接返回完整 `EditDraft`。

---

## 5. Errors

```ts
type EditDraftPatchErrorCode =
  | "PATCH_INVALID"
  | "PATCH_TARGET_NOT_FOUND"
  | "PATCH_CONFLICT"
  | "PATCH_NOT_APPLICABLE";

interface EditDraftPatchError {
  code: EditDraftPatchErrorCode;
  message: string;
  failed_op_id?: string | null;
}
```

---

## 6. 一句话结论

`EditDraftPatch` 的本质，是 agent 的标准执行输出，而不是解释文本。 
