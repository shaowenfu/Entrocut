# 2026-04-14 三个 MVP PR 合并与联调计划日志

## 今日目标

完成三件事：

1. 把三个独立 PR 按最小风险顺序合到同一条本地 integration branch。
2. 以任务文档的北极星目标为准绳，验证合并后的主链没有被冲突破坏。
3. 为下一阶段人工 `MVP end-to-end integration（端到端联调）` 落一份可直接执行的任务文档。

## 合并背景

本次需要合并的三个 PR 分别对应三条原本分散推进的能力线：

1. 真实桌面导入与检索准备
2. MVP `render / retrieve / inspect / patch / timeline`
3. 桌面端 `core supervisor（本地核心服务托管器）` 与 `PyInstaller` 打包

如果只看文件冲突数量，很容易把这次工作理解成一次普通的 `git merge`。  
但从第一性原理看，本次合并的真正目标不是“把三个分支文本叠起来”，而是：

`让 EntroCut 的桌面 MVP 从“几个能力分别成立”变成“一条从真实素材到真实 preview/export 的连续执行链”。`

## 合并顺序判断

最终采用的顺序是：

1. `PR #5` 真实桌面导入与检索准备
2. `PR #7` MVP 闭环
3. `PR #6` 桌面端一体化打包与托管

原因如下。

### 1. 为什么先合 `PR #5`

`PR #5` 解决的是事实层问题：

1. `create_project` 不再伪造 `assets/clips`
2. `assets:import` 才是唯一真实素材入口
3. `media.files[*].path` 必须是绝对本地路径
4. `auth gating` 提前到 ingest 入口
5. Electron Main 负责目录扫描并返回结构化文件列表

也就是说，它先把“什么是系统可信输入”这个问题钉住了。  
没有这一步，后续 `retrieve / inspect / preview / export` 即使合进来，也可能建立在 fake clips 上。

### 2. 为什么第二个合 `PR #7`

`PR #7` 负责把 agent 执行层从占位推进到可用闭环：

1. `retrieve` 接入真实 server retrieval
2. `inspect` 输出候选证据
3. `patch` 正式化为 `EditDraftPatch`
4. `preview / export` 共用 `RenderPlan`
5. 前端消费 `agent.step.updated` 与 `preview.completed`

这条链天然依赖 `PR #5` 已经把素材事实层收紧。  
但它与 `PR #5` 的真实代码冲突很少，说明两者在职责划分上是正交的。

### 3. 为什么最后合 `PR #6`

`PR #6` 的价值是把已经成立的 `core` 主链封装进桌面产品形态：

1. Electron Main 自动拉起 `core`
2. Renderer 感知 `core runtime state`
3. 打包时携带 `core-dist`
4. 开发态 / 发布态区分启动策略

这条线不应该反过来主导 ingest 与 agent 主链，所以放在最后。  
这样真正需要手工解决的代码冲突只会集中在 Electron 边界层，而不会污染核心业务链路。

## 实际冲突面

通过真实 merge rehearsal 和正式 merge，冲突面最终被压缩为两类。

### 1. 代码冲突

核心代码冲突只发生在：

1. `client/main/main.ts`
2. `client/src/electron.d.ts`

这两个文件都位于 Electron 边界层，说明问题不是业务语义对撞，而是“桌面扫描能力”和“桌面托管能力”同时想占据同一个桥接入口。

### 2. 文档冲突

其余冲突主要发生在：

1. `docs/README.md`
2. `docs/develop_diary/README.md`
3. `server/README.md`

这类冲突本质不是语义互斥，只是多个分支都在同步索引和状态描述，所以采用 `union merge（并集合并）` 即可。

## 关键合并决策

### 1. `client/main/main.ts`

最终口径不是二选一，而是让两种职责并存：

1. 保留 `PR #6` 的 `core supervisor`
2. 保留 `PR #5` 的 `registerFileScannerIpcHandlers()`

也就是说，Main Process 现在同时承担：

1. 本地 `core` 进程托管
2. 目录选择与视频文件扫描
3. `secure credential` 管理
4. `auth deep link` 回流

这符合桌面壳层的职责边界。

### 2. `client/src/electron.d.ts`

这里做的是类型并集，而不是覆盖：

1. 保留结构化 `OpenDirectoryResult`
2. 保留 `CoreRuntimeState`
3. 保留 `getCoreBaseUrl / getCoreRuntimeState / onCoreRuntimeState`

这样 Renderer 既能消费目录扫描结果，也能消费 `core` 启动态。

### 3. `client/main/coreSupervisor.ts`

这里额外做了一个非冲突修正：

1. 开发态优先读取 `CORE_PYTHON_BIN`
2. 否则优先使用仓库内 `core/venv/bin/python`
3. 如果 venv 不存在，再回退到 `python`

原因很简单：

`当前仓库规范要求 Python 项目优先走本地虚拟环境，而不是把 python3 写死。`

## 合并后已验证项

### 1. Core 测试

执行：

```bash
source core/venv/bin/activate
pytest core/tests/test_real_ingest_contract.py core/tests/test_mvp_closure_pipeline.py -q
```

结果：

1. `6 passed`

### 2. Client 构建

执行：

```bash
cd client
npm run build
npm run electron:build-main
```

结果：

1. `vite build` 成功
2. Electron `main/preload` bundling 成功

### 3. Desktop Core 打包

执行：

```bash
source core/venv/bin/activate
cd client
npm run core:build-desktop
```

结果：

1. `PyInstaller` 安装并生效
2. `core/dist/core-dist` 构建完成

## 当前结论

到今天为止，仓库里的三条任务线已经不再是并行存在的三个半成品，而是合成了一条新的本地集成主线：

1. Electron 选择目录并扫描真实视频文件
2. Renderer 把 `files[path]` 送进 `core`
3. `core` 执行真实 ingest / vectorize / retrieval
4. `agent` 能走 `retrieve / inspect / patch / preview`
5. `export` 走真实渲染
6. Electron 可以自动托管本地 `core`

这意味着下一阶段不再是“继续写分支能力”，而是：

`做一轮完整、手工、端到端的 MVP 联调，把真实使用路径从启动到导出走通。`

## 下一步计划

下一步不应该立刻继续大改代码，而应该按任务文档做完整人工联调。

联调目标不是只测某一个 API，而是验证以下整条链：

1. 桌面启动
2. 本地 `core` ready
3. 登录态可用
4. 目录扫描正确
5. ingest 状态推进正确
6. retrieval/inspect 真正命中
7. patch 真正改写 draft
8. preview 产物可播放
9. export 产物可落地
10. 前端 timeline 与错误语义可解释

对应的完整人工联调方案，已单独落盘到：

`docs/tasks/2026-04-14_mvp_manual_end_to_end_integration_plan.md`
