# Local Data Storage Architecture

本文档定义 `EntroCut` 桌面端的数据存储总架构。

目标不是讨论某一个表怎么建，而是固定：

1. 哪些数据属于本地权威事实
2. 哪些数据应进入 `SQLite`
3. 哪些数据应继续留在文件系统
4. 哪些数据必须放进 `Keychain / Credential Manager`
5. `MongoDB Atlas` 在整个系统里到底承担什么角色

本文档主要覆盖 `client + core`，并明确它们和云端的边界。

---

## 1. 第一性原理

对当前项目来说，桌面应用的数据层必须先满足 5 件事：

1. 单机可用
2. 断网后仍能打开项目和继续编辑
3. 原始媒体不必上传云端
4. 本地状态不能只靠前端内存维持
5. 敏感凭证不能和普通业务数据混存

从这 5 个要求直接推出当前最合理的存储组合：

### 本地

1. `SQLite`
2. `File System`
3. `Keychain / Credential Manager`

### 云端

1. `MongoDB Atlas`

这个组合不是习惯选择，而是桌面应用场景下最符合约束的结果。

---

## 2. 当前架构判断

当前 `core` 实际上还是一个 `in-memory state server（内存状态服务）`。

当前真实情况是：

1. `project / edit_draft / chat_turns / task` 主要存在 Python 进程内存
2. `client` 的业务状态主要存在 `Zustand` 内存 store
3. `auth token` 只做了浏览器 `localStorage` 级别保存

这适合原型期，但不适合作为长期本地权威数据层。

因此下一阶段的数据层目标应明确为：

`把 core 从 in-memory state server 升级成 SQLite-backed local backend。`

---

## 3. 存储分层总图

推荐固定为四层。

### 3.1 `Client Memory Layer`

职责：

1. 保存 UI state
2. 保存页面派生状态
3. 保存短生命周期交互状态

典型数据：

1. `LaunchpadState`
2. `WorkspaceState`
3. `AuthStoreState`
4. 各类 `loading / reconnect / isThinking` 状态

特点：

1. 非权威
2. 可丢失
3. 由 `Core` 状态恢复

### 3.2 `Core Durable State Layer`

职责：

1. 保存本地权威业务事实
2. 支撑项目恢复、回放和持续编辑

存储介质：

1. `SQLite`

典型数据：

1. `projects`
2. `assets`
3. `clips`
4. `edit_drafts`
5. `shots`
6. `scenes`
7. `chat_turns`
8. `tasks`
9. `tool_observations`
10. `runtime_state`

### 3.3 `Core Artifact Layer`

职责：

1. 保存原始媒体和大文件产物

存储介质：

1. `File System`

典型数据：

1. 缩略图
2. 关键帧缓存
3. 检索中间产物
4. 预览文件
5. 导出文件
6. 代理文件和其它可重建缓存

### 3.4 `Secure Credential Layer`

职责：

1. 保存敏感认证与密钥

存储介质：

1. `Keychain / Credential Manager`

典型数据：

1. `access_token`
2. `refresh_token`
3. provider secrets
4. 未来需要长期保存的第三方授权令牌

当前实现补充：

1. `client` 在 `Electron` 环境下通过主进程安全桥读写凭证
2. 主进程使用系统 `safeStorage` 加密本地凭证文件
3. `core` 本地只持久化 `access_token / user_id` 镜像，不持久化 `refresh_token`

---

## 4. 为什么本地权威库应该是 SQLite

对 `EntroCut` 这类桌面 AI 应用，本地权威库更适合用 `SQLite`，原因很直接：

1. 不需要用户额外启动服务
2. 文件级可迁移、可备份
3. 单机事务和版本化足够强
4. 对 `project -> draft -> task -> turn` 这类关系数据天然合适
5. 很适合 `Core` 这种本地后端服务模式

相反，本地 `Redis` 不适合做权威事实源，因为它更适合：

1. 临时缓存
2. 短生命周期任务协调
3. 高吞吐易失状态

当前项目并没有强到必须引入本地 `Redis` 的需求。

结论：

1. `SQLite` 是本地权威业务数据库
2. `Redis` 如果未来出现，也只能是可选缓存层，不是事实源

---

## 5. 为什么文件系统必须独立存在

原始媒体和大文件产物不应进入 `SQLite BLOB` 主链。

原因：

1. 视频文件太大
2. 预览和导出文件天然是文件系统对象
3. 素材路径本来就是桌面应用的重要上下文
4. 本地渲染工具链和媒体处理工具天然围绕文件工作

因此正确做法是：

1. `SQLite` 只存结构化元数据和索引引用
2. 原始素材默认只保存引用，不复制到项目目录
3. 文件系统只保存项目中间产物和最终产物

例如：

1. `assets.source_path`
2. `preview_cache.path`
3. `export_result.output_url`

### 5.1 原始素材的默认策略

当前推荐策略很明确：

1. 新建项目时，不复制原始视频/音频文件
2. `Core` 只记录素材路径、文件元数据和必要校验信息
3. 真正落到项目工作目录里的，只是中间文件和产物

原因：

1. 避免双份占用磁盘
2. 符合桌面剪辑软件常见习惯
3. 原始素材本来就常常在用户自己的媒体盘、素材盘、移动硬盘里

未来 `asset` 侧建议至少持久化：

1. `source_path`
2. `file_name`
3. `size_bytes`
4. `modified_at`
5. 可选 `content_hash`

这样即使用户移动文件，也可以支持后续“重新定位素材”。

### 5.2 何时才需要复制原始素材

默认不复制。

只有在以下场景才考虑复制或生成代理文件：

1. 用户显式选择“导入为项目内管理素材”
2. 原始素材位于不稳定介质，比如临时挂载目录
3. 需要生成代理文件以支持低性能机器上的流畅预览

即使发生复制，也应明确区分：

1. `reference media`
2. `managed copy`
3. `proxy media`

默认模式仍应是：

`reference-only`

---

## 6. 为什么凭证必须从普通存储里分离

`access_token / refresh_token / provider secret` 不应和普通业务表混在一起，也不应长期停留在前端 `localStorage`。

原因：

1. 安全边界不同
2. 生命周期不同
3. 轮换机制不同
4. 泄露风险不同

因此：

1. `SQLite` 存业务事实
2. `Keychain / Credential Manager` 存凭证

在 `client` 里，`localStorage` 最多只能作为原型阶段的过渡实现。

当前落地口径：

1. `client` 启动时优先读取安全存储
2. 若检测到旧 `localStorage` token，则一次性迁移后清理
3. 新 token 写入只走安全存储
4. `core` 通过本地 `auth session` 表保存 `access_token / user_id` 镜像，供本地后端请求 `server` 使用

---

## 7. 云端 MongoDB Atlas 的职责边界

`MongoDB Atlas` 在这个架构里不是桌面端事实源，也不是本地项目数据库替代品。

它只负责：

1. 账号信息
2. 云同步记录
3. 轻量级项目元数据
4. 跨设备可见但不含原始媒体的大纲信息
5. 未来协作/团队相关元数据

它明确不负责：

1. 本地 `EditDraft` 的权威读写
2. 本地媒体索引的全部原始状态
3. 原始视频文件持久化
4. 桌面端无网络情况下的项目恢复

一句话：

`Atlas` 是同步与账号层，不是本地编辑事实层。

---

## 8. client 和 core 的数据职责划分

### 8.1 Client

`client` 只应承担：

1. 视图状态
2. 页面派生状态
3. 短生命周期交互状态

不应承担：

1. 本地权威业务事实
2. 真实项目持久化
3. 复杂 runtime state 的长期保存

### 8.2 Core

`core` 应承担：

1. 本地权威事实层
2. 状态变更入口
3. 任务编排
4. `WebSocket event stream`
5. 数据持久化与恢复

所以未来数据层的真实中心必须是：

`Core + SQLite`

而不是：

`Client + Zustand`

---

## 9. 推荐的本地 SQLite 数据域

当前建议最少分成这些数据域。

### 9.1 项目域

1. `projects`
2. `project_settings`

### 9.2 素材域

1. `assets`
2. `clips`
3. `clip_embeddings` 或独立向量索引引用表

### 9.3 草案域

1. `edit_drafts`
2. `shots`
3. `scenes`
4. `draft_versions`

### 9.4 对话域

1. `chat_turns`
2. `tool_observations`
3. `runtime_state_snapshots`

### 9.5 任务域

1. `tasks`
2. `task_events`

### 9.6 导出与预览域

1. `preview_artifacts`
2. `export_artifacts`

当前不要求你一次性把所有表做完，但后续 schema 应围绕这些域展开。

---

## 10. 推荐的文件系统目录职责

建议未来本地工作区固定为类似结构：

```text
app_data/
  db/
    entrocut.sqlite3
  projects/
    <project_id>/
      thumbs/
      preview/
      exports/
      temp/
      proxies/
  logs/
```

含义：

1. `db/`
   - 本地权威数据库
2. `projects/<project_id>/thumbs/`
   - 缩略图与关键帧缓存
3. `projects/<project_id>/preview/`
   - 预览产物
4. `projects/<project_id>/exports/`
   - 最终导出文件
5. `projects/<project_id>/temp/`
   - 中间处理文件
6. `projects/<project_id>/proxies/`
   - 可选代理文件
7. `logs/`
   - 本地日志

这里刻意不放 `media/` 目录，原因是：

1. 原始素材默认不归项目目录托管
2. 项目目录主要保存“项目生成物”，不是“素材副本”

### 10.1 工作目录和安装目录必须分离

项目工作目录不应放在应用安装目录下。

正确做法是：

1. 安装目录只放程序本体
2. 应用数据目录放本地数据库、缓存、日志和项目中间文件
3. 导出目录由用户在导出时单独决定

这能避免：

1. 默认把大量数据堆进 `C 盘`
2. 升级或卸载应用时误伤项目数据
3. 安装路径和数据路径混在一起

### 10.2 工作目录何时创建、由谁决定

这件事的默认规则应固定如下：

1. 新建项目时自动创建项目工作目录
2. 目录路径由 `Core` 负责决定和创建
3. `Client` 不要求用户手动选择工作目录

原因：

1. 这更符合桌面应用主流体验
2. 用户通常只需要在导出时选择输出目录
3. 工作目录属于内部运行时实现细节，不应成为每次建项目时的用户负担

因此推荐流程是：

1. `client` 调 `create_project`
2. `core` 创建 `project_id`
3. `core` 在全局 `app data root/projects/<project_id>/` 下初始化目录
4. 后续缩略图、预览、中间文件都落到这里

### 10.3 默认工作目录应放在哪

默认应放在系统用户数据目录，而不是让用户首次建项目时手选。

例如：

1. Windows: `%LOCALAPPDATA%/EntroCut/`
2. macOS: `~/Library/Application Support/EntroCut/`
3. Linux: `~/.local/share/EntroCut/`

然后项目级目录固定为：

`<app_data_root>/projects/<project_id>/`

这是更符合主流桌面软件的默认行为。

### 10.4 用户什么时候才需要感知目录

默认只在这两类场景暴露给用户：

1. 导出时选择导出路径
2. 在全局设置里修改缓存盘或应用数据位置

也就是说：

1. `工作目录` 是系统托管的内部目录
2. `导出目录` 才是用户高频主动选择的目录

这和常见剪辑软件的体验更接近。

---

## 11. 推荐的运行时流转

未来正确的数据流应是：

1. `client` 发动作给 `core`
2. 新建项目时，`core` 分配 `project_id` 并初始化项目工作目录
3. `core` 更新 `SQLite`
4. 如需产物，`core` 写项目工作目录
5. 如需鉴权，`core` 从系统安全存储读取令牌
6. `core` 通过 `WebSocket` 把最新状态广播给 `client`
7. 如需云同步，`core/server` 再把轻量元数据同步到 `Atlas`

这条链路里最关键的原则是：

`任何能影响项目事实的状态，都应先经过 core，再进入持久层。`

---

## 12. 当前阶段的最小落地顺序

建议演进顺序如下：

1. 先把 `core` 的 `project / edit_draft / chat_turn / task` 从内存迁到 `SQLite`
2. 同时在 `create_project` 时引入项目工作目录初始化
3. 再把 `runtime state / tool observations` 落盘
4. 再把预览和导出产物目录标准化
5. 再把认证令牌迁出 `localStorage` 到系统安全存储
6. 最后再讨论同步到 `Atlas` 的云元数据模型

这个顺序的好处是：

1. 先解决本地权威事实问题
2. 再解决恢复和同步问题
3. 不会一开始就把系统复杂度拉爆

---

## 13. 一句话结论

`EntroCut` 的本地数据层最佳实践不是 “MongoDB Atlas + 本地 Redis”，而是：

`SQLite + File System + Keychain/Credential Manager`

同时：

`MongoDB Atlas` 只负责同步、账号和云元数据，不负责桌面端本地事实源。`
