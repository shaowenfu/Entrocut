# Local Data Storage Refactor Plan

本文档承接 [02_local_data_storage_architecture.md](./02_local_data_storage_architecture.md) 的原则，把本地数据层改造方向落成可直接执行的工程方案。

目标不是重新讨论架构方向，而是固定实现主路径，减少后续实现阶段的决策开销。

---

## 1. 目标状态

本地数据层改造完成后，系统应固定为以下形态：

1. `client` 不再承担业务事实源，只保留内存视图状态
2. `core` 成为本地权威状态中心
3. 结构化业务事实进入 `SQLite`
4. 原始素材继续保留外部路径引用，不默认复制
5. 项目中间文件进入 `app_data_root/projects/<project_id>/`
6. 敏感凭证从前端 `localStorage` 迁移到系统安全存储
7. `MongoDB Atlas` 仍只负责账号、同步和云元数据

一句话：

`EntroCut` 的本地事实源从 “前端内存 + core 内存” 迁移为 “client 内存视图 + core 持久化状态”。`

---

## 2. 当前状态与差距

当前 `main` 分支上的主要落差如下：

1. [core/server.py](/home/sherwen/MyProjects/Entrocut/core/server.py) 仍由 `InMemoryProjectStore` 持有：
   - `project`
   - `edit_draft`
   - `chat_turns`
   - `active_task`
   - `export_result`
   - `sequence`
2. `CoreAuthSessionStore` 仍是进程内内存态，不具备重启恢复能力
3. [client/src/services/httpClient.ts](/home/sherwen/MyProjects/Entrocut/client/src/services/httpClient.ts) 和 [client/src/services/authClient.ts](/home/sherwen/MyProjects/Entrocut/client/src/services/authClient.ts) 仍用 `localStorage`
4. 项目工作目录尚未成为正式运行时概念
5. 当前 `HTTP API` 和 `WebSocket event stream` 已经足够稳定，可以继续复用，不需要先改对外契约

当前最重要的判断不是“功能缺很多”，而是：

`core` 已经具备本地后端形状，但缺少真正的持久化后端与工作目录层。`

---

## 3. 分阶段改造方案

改造按 4 个阶段推进，避免一步到位大改。

### 第一阶段：本地持久化骨架

目标：

1. 在 `core` 内引入本地数据层模块
2. 固定 `SQLite` 文件和 `app data root` 的位置规则
3. 在 `create_project` 时初始化项目工作目录
4. 保持现有 API 和 WS 事件名不变
5. 保持任务调度逻辑基本不变，只先替换状态存储后端

建议模块边界：

1. `storage_paths`
   - 负责 `app data root`
   - 负责 `db path`
   - 负责 `project workspace dir`
   - 负责常见产物路径生成
2. `sqlite connection`
   - 负责数据库连接、初始化和基础事务边界
3. `repository`
   - 负责 `project / draft / turn / task / runtime` 的读写
4. `workspace manager`
   - 负责项目工作目录初始化
   - 负责目录存在性和基础布局

这一阶段的重点不是范式化，而是：

`先把 core 的状态事实源替换成可持久化的本地后端。`

### 第二阶段：核心业务事实落库

目标：

1. `projects`
2. `edit_drafts`
3. `chat_turns`
4. `tasks`
5. `export_result`
6. `sequence` 或事件游标

固定要求：

1. 第一版允许“半规范化”落地
2. `EditDraft` 相关结构允许先用 JSON 存储
3. 优先保证恢复性和一致性，再追求完全范式化

建议默认策略：

1. `Project` 独立表
2. `EditDraft` 主体作为 JSON 存在 `edit_drafts.draft_json`
3. `assistant turn / task details / export result` 允许 JSON 存储
4. 后续再逐步细拆 `shots / scenes / clips`

### 第三阶段：工作目录与产物管理收口

目标：

1. 统一 `app data root`
2. 统一 `project workspace dir`
3. 所有缩略图、预览、导出、代理文件都由独立路径模块生成
4. 明确不默认复制原始素材
5. 为未来“重新定位素材”预留元数据字段

这一阶段要把“文件应该写到哪”从业务逻辑里抽离出来，避免：

1. 在业务代码里手拼路径
2. 安装目录和数据目录混用
3. 各种临时文件落点不一致

### 第四阶段：凭证迁移

目标：

1. `access_token`
2. `refresh_token`
3. 未来 provider secrets

固定要求：

1. 前端不再以 `localStorage` 为长期方案
2. `core` 或 Electron 层通过系统安全存储读写凭证
3. 迁移期允许兼容旧 token 读取，但新写入走安全存储

这一阶段不阻塞数据库落地，但应在本地数据层主线稳定后尽快推进。

---

## 4. 本地目录设计

目录规则固定如下：

```text
app_data_root/
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

目录职责：

1. `db/entrocut.sqlite3`
   - 本地权威数据库
2. `projects/<project_id>/thumbs/`
   - 缩略图与关键帧缓存
3. `projects/<project_id>/preview/`
   - 预览文件
4. `projects/<project_id>/exports/`
   - 导出文件
5. `projects/<project_id>/temp/`
   - 中间处理文件
6. `projects/<project_id>/proxies/`
   - 可选代理文件
7. `logs/`
   - 本地日志

明确约束：

1. 项目工作目录在 `create_project` 时创建
2. 路径由 `core` 决定
3. `client` 不要求用户在新建项目时手动选择工作目录
4. 用户高频选择的是导出目录，不是工作目录
5. 安装目录和数据目录必须分离

推荐默认根目录：

1. Windows: `%LOCALAPPDATA%/EntroCut/`
2. macOS: `~/Library/Application Support/EntroCut/`
3. Linux: `~/.local/share/EntroCut/`

---

## 5. 原始素材与项目工作目录的边界

默认原则：

1. 原始素材只做路径引用
2. 不复制进项目工作目录
3. 项目工作目录只保存中间产物和导出产物

`asset` 侧建议至少持久化这些信息：

1. `source_path`
2. `file_name`
3. `size_bytes`
4. `modified_at`
5. 可选 `content_hash`

这样后续可以支持：

1. 素材丢失检测
2. 重新定位素材
3. 路径变更后的恢复

只有以下场景才考虑复制或生成新文件：

1. 用户显式选择“托管素材”
2. 素材位于不稳定介质
3. 需要代理文件支持低性能机器预览

默认模式固定为：

`reference-only`

---

## 6. SQLite 最小数据模型

第一版不追求重 ORM 或复杂迁移系统，优先用轻量方式把本地事实落盘。

至少定义这些逻辑表。

### 6.1 `projects`

建议字段：

1. `id`
2. `title`
3. `workflow_state`
4. `workspace_dir`
5. `created_at`
6. `updated_at`

### 6.2 `edit_drafts`

建议字段：

1. `project_id`
2. `draft_id`
3. `version`
4. `status`
5. `draft_json`
6. `created_at`
7. `updated_at`

默认选择：

1. 第一阶段 `EditDraft` 主体直接用 `draft_json`
2. `shots / scenes / clips / assets` 不强制立即拆表

### 6.3 `chat_turns`

建议字段：

1. `id`
2. `project_id`
3. `role`
4. `turn_type`
5. `payload_json`
6. `created_at`

### 6.4 `tasks`

建议字段：

1. `id`
2. `project_id`
3. `type`
4. `status`
5. `progress`
6. `message`
7. `created_at`
8. `updated_at`

### 6.5 `project_runtime`

建议字段：

1. `project_id`
2. `active_task_id`
3. `export_result_json`
4. `sequence`
5. `updated_at`

### 6.6 `assets`

建议字段：

1. `id`
2. `project_id`
3. `source_path`
4. `file_name`
5. `size_bytes`
6. `modified_at`
7. `content_hash`
8. `created_at`

这个表的目标不是替代 `draft_json`，而是给素材引用与后续“重新定位素材”留正式落点。

---

## 7. 代码改造边界

后续实现时必须固定以下边界，避免顺手把改造面扩散。

1. `client` 继续通过现有 `HTTP + WebSocket` 和 `core` 通信
2. 不让 `client` 直接感知数据库
3. `core/server.py` 先做“存储后端替换”，不顺手重写全部业务逻辑
4. `InMemoryProjectStore` 应逐步替换成：
   - `repository`
   - `runtime service`
   - `event publisher`
5. 工作目录创建、路径生成、文件落点统一走独立模块
6. 凭证迁移是单独阶段，不阻塞数据库落地

换句话说，第一版不是“重写 core”，而是：

`在保持现有接口和主业务流程的前提下，替换底层状态存储方式。`

---

## 8. 兼容性与迁移策略

当前改造固定以下兼容原则：

1. 现有 `HTTP API` shape 不变
2. 现有 `WebSocket` 事件名不变
3. 现有测试主线继续保留
4. 本地首次启动时可自动初始化数据库和目录
5. 当前无正式历史数据迁移需求，可不做复杂 migration framework
6. 若发现旧 token 仍在 `localStorage`，可一次性迁移并清理

这意味着第一阶段实现者不需要同时处理：

1. API 版本迁移
2. UI 重写
3. 复杂历史库升级路径

---

## 9. 测试要求

后续实现必须至少覆盖以下测试目标。

### 9.1 项目与目录

1. 新建项目时会创建数据库记录
2. 新建项目时会初始化项目工作目录
3. 工作目录结构符合约定

### 9.2 素材引用

1. 原始素材导入后只记录路径引用
2. 不复制原始素材文件
3. 丢失路径时可检测并给出错误语义

### 9.3 持久化恢复

1. 重启 `core` 后仍能读取已有项目
2. 草案状态能恢复
3. 聊天历史能恢复
4. 任务状态能恢复

### 9.4 现有主链兼容

1. `chat / import / export` 路径在持久化后端下仍保持原有 API 语义
2. 事件流 `sequence` 连续
3. `workspace snapshot` 与持久化状态一致

### 9.5 凭证迁移

凭证迁移阶段至少验证：

1. 可从旧 `localStorage` 读取
2. 可写入系统安全存储
3. 旧存储可清理

---

## 10. 默认假设

后续实现默认按以下假设执行，不再重新决策：

1. 当前 `main` 上的 `HTTP API` 和 `WebSocket` 契约继续保留，不做接口级重构
2. 第一版本地数据库优先选择 Python 标准 `sqlite3` 或轻量封装，不引入重 ORM 作为前置条件
3. 第一阶段允许 JSON 列承载 `EditDraft` 等复杂结构
4. 项目工作目录由 `core` 决定，不要求用户在新建项目时选择
5. 原始素材默认只做引用管理，不做复制
6. 凭证迁移放在数据库落地之后执行，不阻塞主线

---

## 11. 实施顺序建议

为了降低风险，建议按这个顺序推进：

1. 先引入 `storage paths + sqlite init + workspace manager`
2. 再把 `project / edit_draft / chat_turn / task / runtime` 持久化
3. 再把现有 `InMemoryProjectStore` 行为迁到 repository 驱动
4. 再统一预览、导出、缓存的文件落点
5. 最后做凭证迁移

这个顺序的核心好处是：

1. 先解决“状态能否持久化”
2. 再解决“文件写到哪里”
3. 最后解决“凭证怎么安全落地”

不让三条主线同时互相阻塞。
