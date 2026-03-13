# Preview Tool Contract

本文档定义 `preview` 工具的字段级契约。

它的作用是：

`把当前 EditDraft 的某个版本，转成用户可审阅的结果引用。`

---

## 1. 设计原则

`preview` 是审阅输出，不是最终导出。

所以它必须表达：

1. 预览的是哪一版草案
2. 预览的是全局还是局部
3. 结果引用是什么

---

## 2. Request

```ts
type PreviewScope = "global" | "scene" | "shot";

interface PreviewOptions {
  quality?: "draft" | "standard";
  muted?: boolean;
}

interface PreviewToolRequest {
  project_id: string;
  draft_id: string;
  draft_version: number;
  scope: PreviewScope;
  scene_id?: string | null;
  shot_id?: string | null;
  options?: PreviewOptions;
  requested_at: string;
}
```

---

## 3. Response

```ts
interface PreviewArtifact {
  url: string;
  thumbnail_url?: string | null;
  duration_ms: number;
}

interface PreviewToolResponse {
  project_id: string;
  draft_id: string;
  draft_version: number;
  scope: PreviewScope;
  artifact: PreviewArtifact;
  responded_at: string;
}
```

---

## 4. Errors

```ts
type PreviewErrorCode =
  | "PREVIEW_INPUT_INVALID"
  | "PREVIEW_RENDER_FAILED"
  | "PREVIEW_ASSET_MISSING"
  | "PREVIEW_VERSION_MISMATCH";

interface PreviewToolError {
  code: PreviewErrorCode;
  message: string;
}
```

---

## 5. 一句话结论

`preview` 的本质，是把“当前草案版本”转成“当前可被用户反馈的结果引用”。 
