# Inspect Tool Contract

本文档定义 `inspect` 工具的字段级契约。

`inspect` 现在只服务一件事：

`作为文本 Agent 的眼睛，描述一个已知 clip 的可见画面内容。`

比较、排序、选择、是否适合当前剪辑目标等判断，全部交给主 `Agent` 在拿到描述后完成。

---

## 1. 设计原则

1. `inspect` 只描述一个已知 `clip`
2. `inspect` 不做候选比较、不做重排、不做选择
3. `inspect` 的调用本质是一次 `VLM（多模态大模型）` 调用：`prompt + image`
4. `inspect` 返回的描述必须持久化绑定到对应 `clip`
5. 同一个 `clip` 多次描述时，直接把新描述追加到字符串字段，不引入数组或复杂 history

---

## 2. Tool Input

```ts
interface InspectInput {
  clip_id?: string;
  clip_alias?: string;
  question: string;
  task_summary?: string;
}
```

约束：

1. `clip_id` 或 `clip_alias` 至少能定位到一个 `clip`
2. `question` 是主 `Agent` 写给视觉模型的问题
3. `task_summary` 只用于帮助视觉模型理解当前观察目的
4. 不再接受 `mode / candidates / ranking / criteria`

---

## 3. Tool Output

```ts
interface InspectOutput {
  clip: Clip;
  source_range: {
    start_ms: number;
    end_ms: number;
  };
  thumbnail_ref?: string | null;
  prompt: string;
  summary: string;
  server_response: {
    clip_id: string;
    description: string;
    uncertainty?: string | null;
    model?: string | null;
  };
}
```

落盘字段：

```ts
interface Clip {
  visual_description?: string | null;
  visual_description_updated_at?: string | null;
}
```

多次描述同一 `clip` 时：

```text
旧描述 + "\n\n" + 新描述
```

---

## 4. Non-goals

当前不做：

1. 不用 `inspect` 选择候选
2. 不用 `inspect` 排序候选
3. 不保存描述数组
4. 不把完整视频交给 server

---

## 5. 一句话结论

`inspect` 是主 `Agent` 的视觉感知工具，不是决策工具。
