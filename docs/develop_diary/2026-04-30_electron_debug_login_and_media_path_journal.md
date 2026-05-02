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
8. 登录恢复后回到主线，发现 `Launchpad` 点击上传视频时打开的是 Ubuntu file picker（文件选择器），但只能选择 folder（文件夹），不能选择 video file（视频文件）；而 `Workspace` 上传可以选择视频文件。
9. `assets:import` 已成功返回 `Media ingest queued`，clips（切分片段）列表也能生成，说明 `core` 已经拿到了有效本地路径；真正失败的是 renderer（渲染进程）尝试用 `<video src="file:///home/...mp4">` 预览本地视频。
10. `http://127.0.0.1:5173` 的 Vite renderer（渲染进程）直接加载 `file://` 资源会被 Chromium 安全策略拦截，报 `Not allowed to load local resource`。这不是导入链路失败，而是本地媒体预览链路越过了浏览器安全边界。
11. Electron 原生 dialog（文件弹窗）在 Linux/Ubuntu 环境下不应假设 `openFile` 和 `openDirectory` 一定能在同一个弹窗里稳定混选，因此需要在 UI 上给出明确的 `Browse Videos` 和 `Browse Folder` 两条入口。

## 处理结果

1. `preload` 改为 CommonJS（通用 JS 模块）产物 `preload.cjs`，`main` 显式加载它。
2. `electron:build-main` / `electron:watch-main` 拆分构建 `main.js` 和 `preload.cjs`，并开启 sourcemap（源映射）。
3. 文件导入链路统一把 Electron 的文件引用收敛到 `files[path]`，并补充 WSL UNC path 到 Linux path 的归一化。
4. OAuth 外部 URL 打开方式从 `explorer.exe <url>` 改为 `cmd.exe /c start "" <url>`。
5. Electron 开发模式禁用 GPU，并在窗口加载后显式 `center/show/focus`。
6. `.vscode/launch.json` 增加 Electron renderer attach（渲染进程附加调试）与 `Main + Renderer` 组合调试入口。
7. dev Electron 登录链路改为 polling（轮询）：浏览器完成 OAuth 后回到 `127.0.0.1:5173`，桌面端用 `login_session_id` 轮询并领取 token，避免依赖 Windows `entrocut://` 注册项。
8. `safeStorage.isEncryptionAvailable()` 不可用时，仅在开发环境写入单独的 `secure-credentials.dev.json` fallback（兜底）文件；production（生产环境）仍使用加密存储。
9. `Launchpad` Electron 上传入口调整为支持视频文件和媒体文件夹：主 drop zone（拖放区）点击优先选择视频文件，操作区新增 `Browse Videos` 和 `Browse Folder` 两个明确按钮。
10. 文件夹导入改为 recursive scan（递归扫描），只收集 `.mp4/.mov/.m4v/.webm/.mkv/.avi` 视频文件，自动跳过子文件夹中的非视频文件；最终仍把具体视频文件作为 `media.files[]` 传给 `core`，不把 `folder_path` 作为直接 ingest（导入）输入。
11. 新增 Electron-only `entrocut-media://` local media protocol（本地媒体协议）。renderer（渲染进程）把本地视频 path（路径）交给 preload（预加载脚本）和 main process（主进程）登记，main process 校验绝对路径、文件存在、视频扩展名后返回 tokenized URL（令牌化 URL）。
12. `localMediaRegistry` 不再把本地 path 转成 `file://`，而是把 Electron 文件引用注册为 `entrocut-media://...`，供 `<video>` 和 thumbnail（缩略图）生成使用。
13. `entrocut-media://` 协议在 main process（主进程）内支持 HTTP `Range`（范围请求）语义，便于视频播放器按片段读取和拖动进度条。
14. 按类型拆分提交：
    - `8c050d4 chore: 完善 Electron 调试与开发登录配置`
    - `c400e7b feat: 支持 Electron 本地视频导入与安全预览`

## 调试经验

1. React component（组件函数）反复进入通常只是 state 变化导致的 render（渲染），不是 async flow（异步流程）倒退。
2. 登录链路应按 `AccountMenu -> useAuthStore -> authClient -> electronBridge -> ipcMain` 逐层断点。
3. 桌面端本地文件路径必须由 Electron Main/Preload 边界提供，不能依赖普通 browser `File` 对象。
4. 在 WSL 环境里，Windows path、Linux path、默认浏览器打开策略必须显式处理，不能假设 Electron/Explorer 会自动做正确转换。
5. `client/src/**/*.ts(x)` 属于 renderer（渲染进程），需要 attach 到 Electron remote debugging port（远程调试端口）；`main.ts/preload.ts` 才走 Node/Electron Main 调试。
6. WSL dev 登录不要依赖 production deep link（生产深链）行为；dev-only polling 更稳定，也不会影响打包后的用户登录体验。
7. 判断“拿不到视频路径”时要拆开看：`assets:import` 成功并生成 clips，说明 ingest（导入）路径链路是通的；`file://` 预览失败属于 renderer resource loading（渲染进程资源加载）问题。
8. 桌面端本地文件预览不应关闭 `webSecurity`（网页安全策略）来绕过限制；更合理的边界是 main process（主进程）提供受控 protocol（协议）或 stream（流），renderer（渲染进程）只消费受控 URL。
9. `folder_path` 是用户选择语义，不应直接成为 core ingest API（导入 API）的输入；core 更稳定的契约是明确的 `media.files[].path` 列表。
10. Electron dialog（文件弹窗）能力和平台有关，尤其 WSLg/Linux 下要避免把“文件和文件夹混选”作为唯一入口；UI 上拆成两个按钮更可预期。
