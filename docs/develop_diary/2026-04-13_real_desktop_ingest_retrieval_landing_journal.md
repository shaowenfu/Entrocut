# 2026-04-13 真实桌面导入与检索准备收敛日志

## 今日目标

落实「真实视频导入与检索准备」主链，核心是三件事：

1. 清理 `create_project` 阶段 fake clips 注入
2. 把 Electron 目录选择改为“主进程扫描后返回 `files[path]`”
3. 收紧 `assets:import` 的 auth 与路径契约，让错误在入口可预期暴露

## 实施摘要

### 1) Core 事实源收敛

- `create_project` 改为空草稿初始化，不再根据媒体输入生成占位 `assets/clips`
- 移除 `folder_path -> fake mp4` 兜底逻辑
- `assets:import` 增加入口鉴权与文件路径校验（绝对路径、存在、非目录）

结果：`retrieval_ready` 只能在真实 ingest + vectorize 成功后派生。

### 2) Electron 目录扫描重构

- 新增 `client/main/fileScanner.ts` 独立封装扫描逻辑
- `main.ts` 仅做 IPC 注册，避免与其他并行改动冲突
- `preload` 与 renderer 统一消费结构化文件引用对象

结果：桌面导入主契约从“目录字符串”收敛为“真实文件列表”。

### 3) 测试补齐

- 新增 `core/tests/test_real_ingest_contract.py`
- 覆盖：
  - 创建项目不再注入 fake clips
  - 导入入口 auth gating
  - 目录路径误传错误语义
  - 成功导入后进入 `retrieval_ready`

## 关键判断

1. 入口严格失败（auth/path）优于中途失败，便于 UI 稳定提示
2. `folder_path` 可保留兼容字段，但不能进入真实 ingest 管线
3. Launchpad/Workspace 的导入语义必须继续向同一条 `assets:import` 主链收敛

## 后续待办

1. 增加 Electron `fileScanner` 独立单测（含空目录/混合文件场景）
2. 迁移旧集成测试中“创建即有 clips”的历史假设
3. 明确目录扫描是否递归子目录，并文档化为可配置策略
