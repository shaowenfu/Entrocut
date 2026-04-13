# 2026-04-13 桌面端 Core 托管与打包落地日志

## 今日目标
把桌面端从“手动启动 core”推进到“主进程自动托管 core”，同时补齐可执行打包与文档链路。

## 实现摘要
1. **Core 打包链路落地**
   - 增加 `core/desktop_entry.py` 作为桌面可执行入口。
   - 增加 `core/pyinstaller.spec`，采用单目录输出。
   - 增加 `core/scripts/build_desktop_core.sh`，统一产物为 `core-dist`。

2. **Electron Main 托管器落地**
   - 新增 `client/main/coreSupervisor.ts`。
   - 支持动态端口、环境变量注入、`/health` 探活、状态机、优雅退出。
   - 开发态默认 `python3 -m uvicorn`，发布态默认拉起 `resources/core-dist/entrocut-core(.exe)`。

3. **Renderer 动态接入落地**
   - 通过 `preload + IPC` 暴露 `core` 运行时状态与 base url。
   - `coreClient` 支持运行时注入 base url。
   - App 新增桌面启动门禁（starting/failed/ready）。

4. **打包流程并入构建命令**
   - `client/package.json` 新增 `core:build-desktop`。
   - `electron:build:*` 前置 Core 构建。
   - `electron-builder.yml` 增加 `extraResources`，将 `../core/dist/core-dist` 打入安装包。

## 关键取舍
1. **保持边界**：Main 只做托管，不承载 core 业务。
2. **避免冲突**：将复杂逻辑封装在 `coreSupervisor.ts`，`main.ts` 仅做注册接线。
3. **先稳定再优化**：第一版以可用和可诊断为优先，重启策略与细粒度错误分级留待后续。

## 验证结果
1. `npm run electron:build-main` 通过。
2. `npm run typecheck` 通过。
3. `build_desktop_core.sh` 在未安装 pyinstaller 的环境中给出明确依赖提示，行为符合预期。

## 后续事项
1. 在三平台环境补齐 PyInstaller 真实依赖收集与烟测。
2. 增加 Main->Renderer 启动失败诊断信息（stderr 摘要/错误码）。
3. 将桌面一体化链路接入 CI，形成可回归发布基线。
