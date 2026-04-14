# EntroCut MVP 手动端到端联调任务文档

日期：`2026-04-14`  
文档定位：任务执行文档  
适用对象：负责手工完成 `desktop + core + server` 联调的操作者  
使用方式：按阶段顺序执行，逐项记录结果；任何失败都先定位在“哪一层契约断裂”，再决定是否改代码

---

## 1. 文档目标

本任务文档不是再做功能开发，而是指导你完成一轮真正的 `MVP end-to-end integration（端到端联调）`。

本轮联调的唯一北极星目标是：

`从桌面应用启动开始，手工走完整条真实主链：本地 core 启动 -> 登录 -> 目录扫描 -> 真实 ingest -> chat -> retrieve/inspect/patch -> preview -> export，并验证前后端全过程可解释。`

如果这轮联调完成，EntroCut 的当前本地 MVP 就不再只是“模块都能单独跑”，而是“真实用户路径可连续跑通”。

---

## 2. 联调完成定义

本轮联调完成的标准如下。

### 2.1 用户视角完成定义

你可以手工完成以下操作且结果正确：

1. 启动桌面端应用。
2. 等待本地 `core` 自动启动并 ready。
3. 完成登录，保证 `core -> server` 可用。
4. 选择本地视频目录。
5. 看到素材进入 `segmenting -> vectorizing -> ready`。
6. 向 `agent` 发送自然语言剪辑指令。
7. 看到 `Agent Timeline` 展示真实执行步骤。
8. 看到并播放真实 `Draft Preview`。
9. 导出真实视频文件并成功落盘。

### 2.2 系统视角完成定义

系统在联调中必须满足：

1. Electron Main 扫描目录，而不是把目录路径直接当视频文件。
2. `assets:import` 只接受真实 `media.files[*].path`。
3. 缺少登录态时，ingest 在入口就失败。
4. `retrieval_ready` 只由真实切分 + 真实向量写入成功派生。
5. `retrieve` 真正调用 `server /v1/assets/retrieval`。
6. `patch` 真正改写 `EditDraft`。
7. `preview` 与 `export` 共用 `RenderPlan`。
8. 前端能收到并展示 `agent.step.updated` 与 `preview.completed`。

---

## 3. 明确 Non-goals

本轮联调明确不做：

1. 不做大规模自动化回归平台搭建。
2. 不做视觉 polish。
3. 不做复杂 prompt 调优。
4. 不做渲染性能优化。
5. 不做检索排序策略优化。
6. 不做生产部署演练。

本轮只回答一个问题：

`当前本地 MVP 主链到底能不能被真实用户路径走通。`

---

## 4. 联调前准备

## 4.1 代码基线

确保当前本地分支已经包含：

1. 真实桌面导入链
2. MVP `render/retrieve/inspect/patch/timeline`
3. 桌面端 `core supervisor` 与 `PyInstaller` 打包能力

建议在开始前确认：

```bash
git status --short --branch
git log --oneline --graph --decorate -n 12
```

目标：

1. 工作树干净
2. 当前分支就是你要验证的集成分支或 `main`

## 4.2 依赖准备

### Core

```bash
source core/venv/bin/activate
pip install -r core/requirements.txt
```

如需要桌面打包验证：

```bash
source core/venv/bin/activate
pip install pyinstaller
```

### Client

```bash
cd client
npm install
```

### Server

按你当前 server 运行方式准备依赖与配置。  
关键点不是“怎么部署”，而是以下能力可用：

1. `POST /v1/assets/vectorize`
2. `POST /v1/assets/retrieval`
3. `POST /v1/chat/completions`
4. 鉴权链路可用

## 4.3 配置准备

你至少需要确认以下配置项可用：

### Client / Electron

1. `VITE_DEV_SERVER_URL`
2. 如需跳过托管 core：`ENTROCUT_SKIP_MANAGED_CORE=1`
3. 如需指定 Python：`CORE_PYTHON_BIN`

### Core

1. `ENTROCUT_APP_DATA_ROOT`
2. `CORE_PORT`
3. `SERVER_BASE_URL`

### Server

1. 鉴权配置
2. 向量服务配置
3. 上游模型配置

## 4.4 联调素材准备

准备一个专门的本地视频目录，建议满足：

1. 目录内至少 `2-5` 个视频文件
2. 每个视频文件时长 `5-60s`
3. 内容差异足够明显，方便检索验证
4. 文件路径不包含过于奇怪的权限与挂载行为

建议额外准备两组异常素材：

1. 空目录
2. 含非视频文件的目录

---

## 5. 联调总阶段

本轮建议按 8 个阶段执行：

1. 静态基线检查
2. core 与 client 本地构建检查
3. server 健康与鉴权检查
4. desktop 启动与本地 core 托管检查
5. 真实导入链路检查
6. chat + retrieval/inspect/patch 检查
7. preview/export 检查
8. 异常场景与回归记录

---

## 6. Phase 1：静态基线检查

## 6.1 目标

确认你开始联调前的代码和依赖状态是可解释的。

## 6.2 执行步骤

```bash
git status --short --branch
source core/venv/bin/activate
pytest core/tests/test_real_ingest_contract.py core/tests/test_mvp_closure_pipeline.py -q
cd client
npm run build
npm run electron:build-main
```

## 6.3 通过标准

1. `core` 测试通过
2. `client` build 成功
3. Electron Main / Preload bundling 成功

## 6.4 失败时如何判断

1. 如果 `core` 测试失败，先不要启动 GUI，先修事实层或 agent 层
2. 如果 `client` build 失败，先修类型与状态消费层
3. 如果 `electron:build-main` 失败，先修 `main/preload/IPC` 边界

---

## 7. Phase 2：Server 健康与鉴权检查

## 7.1 目标

确保真正阻塞 ingest / retrieval 的不是桌面端，而是 server 端配置是否成立。

## 7.2 执行步骤

启动 server 后，确认：

```bash
curl http://127.0.0.1:<server_port>/health
```

然后验证以下能力至少有一种成立：

1. 正常 OAuth 登录可完成
2. 你有可用的测试 token
3. 你能在 UI 中看到登录成功后的用户状态

## 7.3 通过标准

1. server `/health` 正常
2. 桌面登录能换回有效登录态
3. 后续 ingest 时不会在入口立刻报 `AUTH_SESSION_REQUIRED`

## 7.4 关键记录项

记录：

1. 登录方式
2. 测试账号
3. token 获取方式
4. server base url

---

## 8. Phase 3：Desktop 启动与本地 Core 托管检查

## 8.1 目标

验证桌面应用是否真的自动托管本地 `core`，而不是你误以为它在自动启动，实际上仍在连一个外部手工服务。

## 8.2 推荐执行方式

开发态验证建议使用：

```bash
source core/venv/bin/activate
cd client
npm run electron:dev
```

如果你要验证“托管关闭时是否能接外部 core”，再单独做：

```bash
export ENTROCUT_SKIP_MANAGED_CORE=1
export VITE_CORE_BASE_URL=http://127.0.0.1:8000
cd client
npm run electron:dev
```

## 8.3 观察点

启动后重点看：

1. UI 是否先展示“正在启动本地核心服务”
2. ready 后是否进入正常页面
3. 如果启动失败，是否有明确错误态
4. `core` 日志是否确实由 Electron Main 拉起

## 8.4 通过标准

1. 在未手工启动 core 的情况下，Electron 仍能进入 ready
2. Renderer 能拿到动态 `core base url`
3. 退出应用时，托管的 `core` 能一起退出

## 8.5 失败分流

1. 启动页卡住：先查 `coreSupervisor`
2. 启动页消失但 API 全 404：查 `base url`
3. 退出后进程残留：查 `stopCore`

---

## 9. Phase 4：真实导入链路检查

## 9.1 目标

验证“目录扫描 -> files[path] -> ingest -> scene detect -> vectorize -> retrieval_ready”这条主链。

## 9.2 正常路径测试

### 步骤 1：创建空项目

在 UI 中创建项目，但不要依赖创建时自动伪造素材。

期望：

1. 项目创建成功
2. 初始 `edit_draft.assets == []`
3. 初始 `edit_draft.clips == []`

### 步骤 2：选择本地目录

点击 `Browse Folder`，选择你准备好的视频目录。

期望：

1. Electron Main 能返回结构化文件列表
2. 非视频文件不会进入 `files[]`
3. `folderPath` 只是上游语义，不会被当作真实视频路径直接提交

### 步骤 3：观察 ingest 状态推进

期望看到：

1. `pending`
2. `segmenting`
3. `vectorizing`
4. `ready`

同时验证：

1. `media_summary.ready_asset_count > 0`
2. `media_summary.indexed_clip_count > 0`
3. `media_summary.retrieval_ready == true`

## 9.3 异常路径测试

### 场景 A：未登录直接导入

操作：

1. 清除登录态
2. 尝试导入素材

期望：

1. 入口直接失败
2. 错误语义是 `AUTH_SESSION_REQUIRED`
3. 不应进入长时间后台 ingest

### 场景 B：空目录

操作：

1. 选择空目录

期望：

1. 不产生成功 ingest
2. UI 给出可解释提示

### 场景 C：目录中包含非视频文件

期望：

1. 非视频文件被扫描层过滤
2. 不影响视频文件正常 ingest

---

## 10. Phase 5：Chat + Retrieval / Inspect / Patch 检查

## 10.1 目标

验证 agent 已经不再只是写占位草稿，而是在消费真实检索结果并回写正式 patch。

## 10.2 推荐测试 Prompt

建议至少测试三类 prompt：

### 类型 A：明确语义检索

示例：

1. “帮我找夕阳、城市、广角的镜头，做一个 8 秒的开场。”
2. “给我挑几个动作感强一点的片段做第一版草稿。”

观察点：

1. 是否触发 `retrieve`
2. 是否返回候选 clip
3. runtime state 是否记录 `candidate_scores`

### 类型 B：要求证据检查

示例：

1. “先看看最相关的候选片段，再决定要不要放进草稿。”

观察点：

1. 是否触发 `inspect`
2. 是否生成 `inspection_summary`
3. timeline 是否能看到这一步

### 类型 C：要求改草稿

示例：

1. “把最相关的两个片段加入当前草稿，做一个 rough cut。”

观察点：

1. 是否触发 `patch`
2. `EditDraft.version` 是否前进
3. `shots/scenes/selected_shot_id` 是否更新

## 10.3 通过标准

1. `retrieve` 来自真实 server retrieval，而不是本地字符串匹配
2. `inspect` 输出 clip + score + summary
3. `patch` 后 `EditDraft` 真实更新
4. 前端 `Agent Timeline` 能看到执行轨迹

## 10.4 失败时如何分层判断

1. 没有候选：先查 ingest 和 retrieval_ready
2. 有候选但 inspect 空：查 clip id 对齐
3. patch 成功但草稿没变：查 `EditDraftPatch` 应用链
4. 后端成功但前端没显示：查事件消费与 Zustand store

---

## 11. Phase 6：Preview 检查

## 11.1 目标

验证当前草稿能产出真实 preview，而不是继续回退到源素材预览。

## 11.2 执行步骤

1. 确保当前草稿中至少有一个 shot
2. 触发 preview 相关链路
3. 在 Workspace 预览区观察来源与播放效果

## 11.3 核心观察点

1. 是否收到 `preview.completed`
2. `preview_result.output_url` 是否是本地产物
3. 预览区标题是否标记为 `Draft Preview`
4. 播放内容是否真的对应当前草稿，而不是源视频

## 11.4 通过标准

1. preview 产物存在
2. preview 可播放
3. preview 内容与当前 `EditDraft.shots` 对齐

## 11.5 重点记录

记录：

1. 当前 draft version
2. preview 输出路径
3. preview 时长
4. 实际体感是否与 shots 总时长一致

---

## 12. Phase 7：Export 检查

## 12.1 目标

验证 export 已切到真实渲染，而不是写一个占位文本文件。

## 12.2 执行步骤

1. 在已有草稿基础上触发导出
2. 等待导出结束
3. 打开导出目录检查产物

## 12.3 核心观察点

1. 是否生成真实视频文件
2. 文件大小是否合理，不是极小的占位文本
3. 输出时长是否与当前 `RenderPlan` 预期一致
4. 导出后 `export_result` 是否更新

## 12.4 通过标准

1. 有真实视频导出产物
2. 产物可播放
3. 与 preview 在内容上基本一致

---

## 13. Phase 8：事件与 UI 语义检查

## 13.1 目标

验证系统不是“后端做了事但 UI 不可解释”，而是全过程对用户可见。

## 13.2 必查事件

联调时至少确认这些事件被正确消费：

1. `task.updated`
2. `workspace.snapshot`
3. `edit_draft.updated`
4. `chat.turn.created`
5. `agent.step.updated`
6. `preview.completed`
7. `export.completed`
8. `error.occurred`

## 13.3 通过标准

1. Agent 执行步骤可见
2. preview/export 状态可见
3. 错误可解释，不是静默失败

---

## 14. 推荐联调记录模板

建议每次联调都按下面的结构记录：

### 14.1 环境记录

1. 分支名
2. commit sha
3. server base url
4. 是否托管 core
5. 测试账号

### 14.2 联调结果

1. 启动：通过 / 失败
2. 登录：通过 / 失败
3. ingest：通过 / 失败
4. retrieval：通过 / 失败
5. inspect：通过 / 失败
6. patch：通过 / 失败
7. preview：通过 / 失败
8. export：通过 / 失败

### 14.3 问题记录

每个问题至少记录：

1. 现象
2. 复现步骤
3. 所在层
4. 期望行为
5. 临时判断

---

## 15. 推荐执行顺序

如果你只做一轮完整手动联调，建议按下面顺序：

1. 静态构建与测试
2. server 健康与登录
3. Electron 启动与 core 托管
4. 正常 ingest
5. 正常 chat -> retrieval/inspect/patch
6. preview
7. export
8. 异常场景回放

原因：

1. 先验证基础设施，再验证用户路径
2. 先跑正常链，再跑错误链
3. 先保证主链成立，再做边界确认

---

## 16. 最终交付物

本轮手动联调结束后，建议至少产出：

1. 一份联调记录
2. 一组截图或录屏
3. 一份问题清单
4. 一份结论

结论建议只回答下面三件事：

1. 当前 MVP 主链是否已成立
2. 当前最阻塞发布体验的三个问题是什么
3. 下一轮应该优先修哪里

---

## 17. 一句话结论

这份联调任务的本质不是“把所有页面点一遍”，而是：

`验证 EntroCut 当前已经合并完成的桌面 MVP，是否真的形成了一条从真实素材到真实导出的连续可解释执行链。`
