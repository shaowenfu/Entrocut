# Entrocut Monorepo 清理方案（仅方案，不执行）

- 文档版本：v1.0
- 生成时间：2026-03-01
- 目的：在不执行任何删除的前提下，给出一次“彻底、可审计、可回滚”的清理方案。

## 1. 目标与边界

### 1.1 清理目标
把当前仓库从“验证链路阶段（Vector Search（向量检索）+ FFmpeg（视频处理）+ Mock API（模拟接口））”重置为干净的 `Monorepo（单仓多包）` 骨架，仅保留：
1. `client/`（前端壳层）
2. `core/`（本地算法服务壳层）
3. `server/`（云端编排服务壳层）

### 1.2 约束
1. 本次只输出方案，不执行任何清理命令。
2. 清理以“移除旧实现与历史痕迹”为优先，不为“可能未来有用”保留遗留代码。
3. 保留最小可启动骨架，不保留验证阶段业务逻辑。

## 2. 当前现状快照（事实）

### 2.1 体量热点
1. `client/` 约 `842M`（主要是 `node_modules`）
2. `core/` 约 `396M`（主要是 `venv`）
3. `server/` 约 `211M`（主要是 `venv`）

### 2.2 明确的遗留特征
1. 多处 `Mock`、`Round`、`0.1.0-mock` 关键字（`core/server/client/scripts/docs` 全面存在）。
2. `core` 存在完整旧 `Pipeline（管线）`：`scene detect -> frame extract -> mock analyze -> edl -> render`。
3. `server` 存在旧 `mock` 路由与大量 `501` 占位路由（`auth/projects/search`）。
4. `client` 存在旧任务流 UI + IPC + 本地 SQLite + sidecar 自动拉起。
5. 根目录仍有历史样例与资产文件（如 `example_vedio.mp4`、PNG 截图）。

### 2.3 工作区状态风险
当前 `git` 工作区非干净状态（已有未提交改动与新增文件），执行清理前必须先做基线快照。

## 3. 清理后的目标结构（Target Tree（目标树））

```text
Entrocut/
  .git/
  .gitignore
  README.md
  docs/                      # 文档保留（如你希望代码仓极简，可在二阶段讨论是否剥离）
  client/
    package.json
    tsconfig*.json
    vite.config.ts
    src/
      main.tsx
      App.tsx
    main/
      main.ts
      preload.ts
  core/
    requirements.txt
    server.py
  server/
    requirements.txt
    main.py
```

说明：上面是“最小可运行骨架”，不包含历史业务代码、历史测试与历史脚本。

## 4. 删除策略（按范围分层）

## 4.1 层 A：环境与构建产物（100% 删除）

1. `client/node_modules/`
2. `client/dist/`
3. `client/dist-main/`
4. `core/venv/`
5. `server/venv/`
6. 全仓 `__pycache__/`
7. `server/.pytest_cache/`
8. `entrocut_jobs/`

理由：全部为可再生产物或运行时垃圾，保留只会污染后续重构。

## 4.2 层 B：根目录遗留物（建议删除）

1. `example_vedio.mp4`
2. `Project.png`
3. `workspace.png`
4. `Mydocs/`
5. `dev.sh`
6. `scripts/`（含 `smoke_test.sh`、`test_server.sh`、`sync-env.sh` 等旧流程脚本）

理由：均绑定旧验证链路或演示资产，不属于新骨架。

## 4.3 层 C：core 旧实现（删除并回填最小壳层）

删除对象：
1. `core/detect/` 全部
2. `core/process/` 全部
3. `core/tests/` 全部

回填对象（最小壳层）：
1. `core/server.py` 仅保留 `health` 与统一错误外壳
2. `core/requirements.txt` 收敛到最小依赖（建议仅 `fastapi`、`uvicorn`、`pydantic`）

## 4.4 层 D：server 旧实现（删除并回填最小壳层）

删除对象：
1. `server/routes/auth.py`
2. `server/routes/projects.py`
3. `server/routes/search.py`
4. `server/routes/mock.py`
5. `server/models/` 全部
6. `server/middleware/` 全部
7. `server/utils/` 全部
8. `server/tests/` 全部
9. `server/DEPLOYMENT.md`
10. `server/Dockerfile`（若你决定“只留本地骨架”）

回填对象（最小壳层）：
1. `server/main.py` 仅保留 `health` 与空路由容器
2. `server/requirements.txt` 收敛到最小依赖

## 4.5 层 E：client 旧实现（删除并回填最小壳层）

删除对象：
1. `client/src/components/` 全部
2. `client/src/hooks/` 全部
3. `client/src/types/` 全部
4. `client/src/assets/` 全部
5. `client/src/test-setup.ts`
6. `client/main/db.ts`
7. `client/main/db.test.ts`
8. `client/main/routes.ts`
9. `client/main/routes.test.ts`
10. `client/main/sidecar.ts`

保留并重写为骨架：
1. `client/src/App.tsx`
2. `client/src/main.tsx`
3. `client/main/main.ts`
4. `client/main/preload.ts`

依赖收敛：
1. 移除与旧链路耦合的库（如 `better-sqlite3`、历史测试依赖、历史 UI 依赖）
2. `package.json` 仅保留壳层运行必需项

## 5. 执行流程（分阶段、可回滚）

## 5.1 Phase 0 - 基线冻结（必须先做）

1. 执行一次完整清单导出：`git status`、`git ls-files`、`du -sh`。
2. 新建保护分支：`cleanup/monorepo-reset`。
3. 对当前状态打标签（Tag（标签））：`pre-cleanup-YYYYMMDD`。

验收：任意时刻可通过分支/标签回到清理前状态。

## 5.2 Phase 1 - 清理可再生产物

1. 删除层 A 全部目录。
2. 校验 `git status` 中不再出现构建产物噪音。

验收：仓库体量显著下降，且无运行时缓存残留。

## 5.3 Phase 2 - 删除遗留根目录资产

1. 删除层 B 全部路径。
2. 更新根 `README.md`，去除旧启动说明。

验收：根目录只剩 monorepo 必要结构与文档。

## 5.4 Phase 3 - 模块级硬清理

1. 执行层 C（core）删除 + 最小壳层回填。
2. 执行层 D（server）删除 + 最小壳层回填。
3. 执行层 E（client）删除 + 最小壳层回填。

验收：`core/server/client` 均能独立启动到 `health` 或基础页面，不含旧业务路径。

## 5.5 Phase 4 - 依赖与配置收敛

1. 清理三端依赖文件，去掉旧验证链路依赖。
2. 统一 `.gitignore`，保证缓存/产物不再入仓。
3. 最小化 `.env.example`，删除无效变量。

验收：安装依赖后可最小启动，且无冗余库。

## 5.6 Phase 5 - 关键词与契约污染扫描

执行全文扫描，必须为 0：
1. `mock`
2. `0.1.0-mock`
3. `Round`
4. `ANALYZING_MOCK`
5. 旧 API 路径（如 `/api/v1/mock`、`/jobs/start`）

验收：旧验证阶段语义完全退出代码主路径。

## 6. 验收标准（Definition of Done（完成定义））

1. 结构验收：仓库只保留干净 `client/core/server` 骨架与必要根文件。
2. 依赖验收：三端依赖最小可运行，不含旧链路库。
3. 语义验收：全仓不存在 `mock/round` 相关实现入口。
4. 启动验收：
   - `client` 可启动空壳界面
   - `core` 返回 `health`
   - `server` 返回 `health`
5. 文档验收：`README` 与 `docs` 只描述新骨架，不描述旧验证流程。

## 7. 风险点与控制

1. 风险：误删仍被引用的入口文件。
控制：每个 Phase 后执行一次启动校验与引用扫描。

2. 风险：当前工作区已有未提交改动，清理会混入历史噪音。
控制：先做 `baseline` 标签与分支隔离，再执行删除。

3. 风险：删除脚本后缺失最小启动方式。
控制：在删除 `dev.sh/scripts` 前，先在 `README` 回填新的最小启动命令。

## 8. 建议的提交切分（便于审查）

1. `chore(cleanup): remove generated artifacts and env caches`
2. `chore(cleanup): remove legacy validation assets and scripts`
3. `refactor(core): reset core to minimal service skeleton`
4. `refactor(server): reset server to minimal service skeleton`
5. `refactor(client): reset client to minimal app shell`
6. `docs: rewrite repo docs for clean monorepo baseline`

---

本方案是“执行前清单”。你确认后，我再按该方案逐 Phase 实施，每个 Phase 单独汇报与停顿确认。
