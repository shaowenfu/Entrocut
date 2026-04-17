# 最终 MVP 全面手动联调执行手册（VS Code + Electron + Local Core + Cloud Server）

日期：2026-04-17  
适用对象：负责最终 `MVP` 端到端人工联调的操作者  
适用范围：`client` 使用 `Electron` 本地调试，`core` 使用 `VS Code debugpy` 本地调试，`server` 固定使用云端 `https://entrocut.sherwenfu.com`

---

## 1. 本次联调的北极星目标

这次联调不是验证某一个局部接口，而是验证完整主链是否闭环：

`用户在 Electron 桌面端登录 -> 导入本地真实视频 -> 本地 core 完成 ingest -> 云端 server 完成 vectorize / retrieval / planner proxy -> agent 推进 draft -> preview -> export -> 最终产出一个完整视频文件`

最终验收不是“页面没报错”，而是：

1. 核心链路全部跑通
2. 最终能在项目工作目录里拿到一个完整的视频文件
3. 问题出现时，能明确定位在 `client / core / server / media asset` 的哪一层

---

## 2. 本次联调拓扑

本次联调必须固定为下面这个拓扑，不要混用其他运行方式：

1. `client`
   - 通过 `VS Code` 本地启动
   - 必须使用 `Electron` 模式
   - 不允许只开网页 `Vite` 页面替代
2. `core`
   - 通过 `VS Code` 本地启动
   - 监听本机 `127.0.0.1:8000`
   - 明确连接云端 `server`
3. `server`
   - 不在本机启动
   - 固定使用：

```text
https://entrocut.sherwenfu.com
```

4. `Electron`
   - 这次联调不使用托管 `managed core（托管 core）`
   - 显式通过 `ENTROCUT_SKIP_MANAGED_CORE=1` 连接外部本地 debug `core`

这样做的原因很直接：

1. 你要求 `core` 也在 `VS Code` 里本地调试
2. 如果让 `Electron Main` 再托管一份 `core`，会形成“双 core”歧义
3. 最终联调阶段最重要的是定位问题边界，而不是验证桌面托管能力

托管 `core` 的验证已经在前一轮集成阶段覆盖过；本轮优先保证主链可观察、可断点、可定位。

---

## 3. 本次联调的非目标

这次联调明确不做这些事情：

1. 不验证 `server` 本地部署流程
2. 不验证桌面安装包内置 `core` 的发布态路径
3. 不验证多项目并行
4. 不验证大规模素材库性能压测
5. 不在这一轮追求所有异常场景都优雅降级

本轮只做一件事：

`把单条真实主链稳定跑到最终视频产出。`

---

## 4. 运行前提

### 4.1 本地依赖前提

你本机至少要满足：

1. `client/node_modules` 已安装
2. `core/venv` 已可用
3. 本地可直接读取待导入视频文件的绝对路径
4. 云端 `server` 当前可用且鉴权链路正常

### 4.2 联调素材前提

建议准备一段便于检索和剪辑的真实视频：

1. 时长建议：`30s - 180s`
2. 内容建议：
   - 有明显主题
   - 有多个镜头或语义段落
   - 便于提出明确剪辑目标
3. 避免：
   - 单镜头纯静态视频
   - 超长大文件
   - 路径包含权限问题或挂载盘不稳定的文件

推荐你准备一份联调输入目标，例如：

```text
请从素材中剪出一个 20 秒左右、节奏紧凑、突出人物演示动作的短视频。
```

---

## 5. VS Code 调试配置约定

这次联调依赖新增后的 `.vscode` 配置，核心约定如下：

### 5.1 Core Debug

`VS Code` 中使用：

```text
Debug Core (FastAPI -> Cloud Server)
```

该入口会：

1. 在本地启动 `core`
2. 固定监听 `127.0.0.1:8000`
3. 注入：

```text
SERVER_BASE_URL=https://entrocut.sherwenfu.com
```

### 5.2 Electron Debug

`VS Code` 中使用：

```text
Debug Client (Electron -> Local Core + Cloud Server)
```

该入口会：

1. 先自动启动 `Vite dev server`
2. 再自动启动 `Electron main/preload` 的 watch 构建
3. 最后真正以 `Electron` 方式启动桌面应用
4. 注入：

```text
VITE_DEV_SERVER_URL=http://127.0.0.1:5173
VITE_CORE_BASE_URL=http://127.0.0.1:8000
VITE_SERVER_BASE_URL=https://entrocut.sherwenfu.com
SERVER_BASE_URL=https://entrocut.sherwenfu.com
ENTROCUT_SKIP_MANAGED_CORE=1
```

注意：

1. 这里的 `SERVER_BASE_URL` 是给 `Electron Main -> local core subprocess env` 保持一致用的
2. 但由于本轮 `ENTROCUT_SKIP_MANAGED_CORE=1`，实际 `Electron` 不会再托管新 core
3. `client` 的业务请求仍以：
   - `VITE_CORE_BASE_URL=http://127.0.0.1:8000`
   - `VITE_SERVER_BASE_URL=https://entrocut.sherwenfu.com`
   为准

---

## 6. 推荐执行顺序

严格按下面顺序执行，不要反过来：

1. 启动 `Debug Core (FastAPI -> Cloud Server)`
2. 等待本地 `core /health` ready
3. 启动 `Debug Client (Electron -> Local Core + Cloud Server)`
4. 在 `Electron` 中完成登录
5. 导入真实视频
6. 等待 ingest 完成
7. 发起 chat 指令，推动 `retrieve / inspect / patch`
8. 生成 preview
9. 执行 export
10. 校验最终视频文件

这个顺序的本质是：

`先让事实层 ready，再让桌面端接入事实层。`

---

## 7. 分阶段联调步骤

## 7.1 阶段 A：Core 启动与云端连接检查

### 操作

在 `VS Code` 中启动：

```text
Debug Core (FastAPI -> Cloud Server)
```

### 必查项

1. 终端里 `uvicorn` 正常启动
2. `127.0.0.1:8000/health` 返回正常
3. `GET /api/v1/runtime/capabilities` 中能看到 `server_base_url`
4. `server_base_url` 必须等于：

```text
https://entrocut.sherwenfu.com
```

### 通过标准

1. `core` 无启动异常
2. 本地 health 正常
3. `core` 已明确指向云端 `server`

### 如果失败，先查

1. `core/venv` 是否可用
2. `launch.json` 中 `SERVER_BASE_URL` 是否正确
3. `core` 启动日志里是否有导入或依赖错误

---

## 7.2 阶段 B：Electron 启动检查

### 操作

在 `VS Code` 中启动：

```text
Debug Client (Electron -> Local Core + Cloud Server)
```

### 必查项

1. `Vite` 任务是否 ready
2. `esbuild watch` 是否 ready
3. `Electron` 桌面窗口是否成功打开
4. 应用是否连接到本地 `core`
5. 没有出现“等待托管 core 启动”的假象

### 通过标准

1. `Electron` 成功启动
2. Renderer 能访问本地 `core`
3. 未额外拉起第二个 `core`

### 如果失败，先查

1. `dist-electron/main.js` 是否已生成
2. `ENTROCUT_SKIP_MANAGED_CORE=1` 是否生效
3. `VITE_CORE_BASE_URL` 是否是 `http://127.0.0.1:8000`
4. 本地 `core` 是否已先启动

---

## 7.3 阶段 C：登录链路检查

### 操作

在 `Electron` 里完成登录。

### 必查项

1. 登录跳转是否成功回流桌面端
2. `core` 本地 `auth session` 是否建立
3. 登录后调用受保护接口是否成功
4. `Workspace` 页面是否进入可操作态

### 通过标准

1. 不再出现 `AUTH_SESSION_REQUIRED`
2. `core -> server` 的鉴权代理正常
3. 之后的 `assets:import / chat / retrieval / export` 可继续执行

### 如果失败，先查

1. 云端 `server` 当前登录回调是否正常
2. `client` 本地 secure store 是否写入成功
3. `core` 的 `DELETE/POST /api/v1/auth/session` 行为是否异常

---

## 7.4 阶段 D：真实素材导入与 ingest 检查

### 操作

1. 在 `Workspace` 里选择本地真实视频
2. 发起导入
3. 等待 ingest 全链路完成

### 必查项

1. 传入的是绝对文件路径，不是目录假路径
2. `assets:import` 成功进入真实 ingest
3. `scene detect` 有真实进度变化
4. `contact sheet` 产物生成
5. `core -> server /v1/assets/vectorize` 调用成功
6. `retrieval_ready` 最终变为 `true`

### 通过标准

1. `asset.processing_stage` 从 `pending/segmenting/vectorizing` 最终进入 `ready`
2. `indexed_clip_count > 0`
3. `media_summary.retrieval_ready = true`
4. `active_tasks` 中的媒体任务成功结束

### 如果失败，先查

1. 本地视频路径是否真实可读
2. `ffmpeg / scenedetect` 相关依赖是否正常
3. `server /v1/assets/vectorize` 是否返回成功
4. 是否是登录态失效导致 `vectorize` 被拒绝

---

## 7.5 阶段 E：Chat / Retrieve / Inspect / Patch 主链检查

### 操作

在 `Electron` 中发起明确的剪辑意图，例如：

```text
请从现有素材中选出最适合做人物演示主线的片段，做一个 20 秒左右、节奏紧凑的版本。
```

### 必查项

1. `chat` 请求成功进入 agent loop
2. `retrieve` 不是本地假匹配，而是真实调云端 `server /v1/assets/retrieval`
3. `inspect` 输出带有候选 clip、score、summary
4. `patch` 成功把结果回写到 `EditDraft`
5. Timeline 中能看到真实 shot 更新

### 通过标准

1. `runtime_state.retrieval_state.last_query` 有值
2. `candidate_clip_ids` 非空
3. `candidate_scores` 非空
4. `inspection_summary` 非空
5. `edit_draft.updated` 事件产生后，UI timeline 明显变化

### 如果失败，先查

1. `retrieval_ready` 是否为 `true`
2. 云端 `server /v1/assets/retrieval` 是否成功
3. `core/inspection.py` 是否对 server 返回做了稳定解析
4. `patch` 后 draft 是否被事实层覆盖或没有正确广播

---

## 7.6 阶段 F：Preview 检查

### 操作

在当前 draft 上触发 preview。

### 必查项

1. preview 任务创建成功
2. `active_tasks` 出现 `preview` 任务
3. `preview.completed` 事件产生
4. 预览文件可播放

### 通过标准

1. `preview_result.output_url` 存在
2. 对应文件真实落盘
3. Electron 内可见预览结果

### 如果失败，先查

1. `RenderPlan` 是否为空
2. 本地 ffmpeg 渲染路径是否可用
3. 预览目录权限是否正常

---

## 7.7 阶段 G：Export 检查

### 操作

在确认 preview 正常后执行 export。

### 必查项

1. export 任务创建成功
2. `active_tasks` 出现 `export` 任务
3. `export.completed` 事件产生
4. 最终导出文件真实存在
5. 文件可播放且内容与当前 draft 相符

### 通过标准

1. `export_result.output_url` 存在
2. 最终文件大小大于 0
3. 最终视频时长与预期大体一致
4. 最终视频不是空白、黑屏或错误拼接

这一步是本轮联调的最终验收点。

---

## 8. 最终验收标准

只有同时满足下面 8 条，才算这轮联调通过：

1. 本地 `core` 能在 `VS Code` 中稳定启动
2. `Electron` 能在 `VS Code` 中以桌面模式稳定启动
3. `client` 成功连接本地 `core`
4. 本地 `core` 成功连接云端 `server`
5. 登录链路正常
6. 真实 ingest 跑通并产生可检索 clip
7. `chat -> retrieve -> inspect -> patch -> preview` 主链跑通
8. 最终成功导出一个完整视频文件

---

## 9. 推荐故障定位顺序

一旦出问题，不要同时改多层，按下面顺序定位：

1. `client` 是否真的跑在 `Electron`，而不是网页模式
2. `client` 是否真的连的是本地 `core`
3. `core` 是否真的指向云端 `server`
4. 登录态是否真的在 `core` 中成立
5. ingest 是否真的完成并让 `retrieval_ready=true`
6. retrieval 返回是否真实且结构稳定
7. patch 后的 draft 是否被正确广播到 UI
8. render/export 是否是本地 ffmpeg 或素材问题

这套顺序的原则是：

`先排连接，再排事实，再排 agent，再排渲染。`

---

## 10. 本轮联调记录模板

建议你手动执行时，按下面模板记录结果：

```md
# 联调记录

## 基本信息
- 日期：
- 操作人：
- 视频素材路径：
- 目标剪辑指令：

## 阶段 A：Core 启动
- 是否成功：
- health：
- server_base_url：
- 备注：

## 阶段 B：Electron 启动
- 是否成功：
- 是否确认 Electron 模式：
- 是否连接 local core：
- 备注：

## 阶段 C：登录
- 是否成功：
- auth session 是否建立：
- 备注：

## 阶段 D：Ingest
- 是否成功：
- indexed_clip_count：
- retrieval_ready：
- 备注：

## 阶段 E：Chat / Retrieve / Inspect / Patch
- 是否成功：
- candidate_clip_ids：
- inspection_summary：
- timeline 是否更新：
- 备注：

## 阶段 F：Preview
- 是否成功：
- preview 文件路径：
- 备注：

## 阶段 G：Export
- 是否成功：
- export 文件路径：
- 文件是否可播放：
- 最终时长：
- 备注：

## 最终结论
- 是否完成完整视频产出：
- 主要问题：
- 下一步：
```

---

## 11. 结论

本轮最终联调的第一性原理不是“把所有模式都试一遍”，而是：

`用最可观察、最可断点、最少歧义的运行拓扑，把 MVP 主链稳定跑到最终视频输出。`

因此这次固定采用：

1. `VS Code debug` 启本地 `core`
2. `VS Code debug` 启 `Electron`
3. 云端固定 `server`
4. 明确禁用 `managed core`

等这条链路彻底跑通，再回头验证“桌面托管本地 core”的发布态体验，才是更稳的推进顺序。
