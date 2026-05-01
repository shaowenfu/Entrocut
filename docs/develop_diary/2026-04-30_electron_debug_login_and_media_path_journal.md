# 2026-04-30 Electron 调试、登录与媒体路径联调记录

本轮联调目标是：本地启动 `client` 和 `core`，使用云端 `server`，通过 `Electron` 启动桌面端并完成登录、选视频、导入素材链路。

## 关键问题

1. `Electron` 选择或拖拽视频后，`core` 收到的 `media.files[].path` 为空，前端报 `INVALID_MEDIA_REFERENCE`。
2. `\\wsl.localhost\Ubuntu\...` 这类 Windows UNC path（网络路径）不能直接交给 WSL 内的 `core` 使用，需要归一化为 Linux absolute path（绝对路径），如 `/home/sherwen/...`。
3. `preload` 原先以 ESM（ECMAScript Module）形式构建，导致 `window.electron` 不稳定，renderer（渲染进程）退回 browser file picker（浏览器文件选择器），只能拿到 `name/size`，拿不到本地路径。
4. WSL 中用 `explorer.exe <url>` 打开 OAuth URL 会进入 Windows 文件管理器，落到 `Documents`，不能可靠打开默认浏览器。
5. WSLg 下 Electron GPU 初始化失败时，窗口可能在任务栏存在但不可见。
6. Windows 侧曾注册过 `entrocut://` protocol handler（协议处理器），OAuth callback（回调）会启动 Windows 里的旧 Electron 应用，而不是当前 WSL dev Electron。
7. WSL/WSLg 环境中 `safeStorage` 可能因为缺少完整 Linux credential backend（凭据后端）而不可用，导致 token 写入时报 `Encryption is not available`。

## 处理结果

1. `preload` 改为 CommonJS（通用 JS 模块）产物 `preload.cjs`，`main` 显式加载它。
2. `electron:build-main` / `electron:watch-main` 拆分构建 `main.js` 和 `preload.cjs`，并开启 sourcemap（源映射）。
3. 文件导入链路统一把 Electron 的文件引用收敛到 `files[path]`，并补充 WSL UNC path 到 Linux path 的归一化。
4. OAuth 外部 URL 打开方式从 `explorer.exe <url>` 改为 `cmd.exe /c start "" <url>`。
5. Electron 开发模式禁用 GPU，并在窗口加载后显式 `center/show/focus`。
6. `.vscode/launch.json` 增加 Electron renderer attach（渲染进程附加调试）与 `Main + Renderer` 组合调试入口。
7. dev Electron 登录链路改为 polling（轮询）：浏览器完成 OAuth 后回到 `127.0.0.1:5173`，桌面端用 `login_session_id` 轮询并领取 token，避免依赖 Windows `entrocut://` 注册项。
8. `safeStorage.isEncryptionAvailable()` 不可用时，仅在开发环境写入单独的 `secure-credentials.dev.json` fallback（兜底）文件；production（生产环境）仍使用加密存储。

## 调试经验

1. React component（组件函数）反复进入通常只是 state 变化导致的 render（渲染），不是 async flow（异步流程）倒退。
2. 登录链路应按 `AccountMenu -> useAuthStore -> authClient -> electronBridge -> ipcMain` 逐层断点。
3. 桌面端本地文件路径必须由 Electron Main/Preload 边界提供，不能依赖普通 browser `File` 对象。
4. 在 WSL 环境里，Windows path、Linux path、默认浏览器打开策略必须显式处理，不能假设 Electron/Explorer 会自动做正确转换。
5. `client/src/**/*.ts(x)` 属于 renderer（渲染进程），需要 attach 到 Electron remote debugging port（远程调试端口）；`main.ts/preload.ts` 才走 Node/Electron Main 调试。
6. WSL dev 登录不要依赖 production deep link（生产深链）行为；dev-only polling 更稳定，也不会影响打包后的用户登录体验。
