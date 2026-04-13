# EntroCut 桌面端一体化发布方案

日期：`2026-04-12`

## 1. 北极星目标

把 `EntroCut` 从“开发者手动启动 `core` + Electron 前端壳”推进到“像 `Cursor`、剪映这类主流桌面应用一样，用户下载安装后双击即可使用”的产品形态。

北极星标准只有一条：

`用户不需要下载仓库、不需要安装 Python、不需要手动运行 uvicorn；应用启动后，桌面端自动拉起本地 core 并完成健康检查。`

---

## 2. 当前问题

当前桌面端只是一个 Electron UI 壳层：

1. `client` 已能打包成安装包
2. 前端默认请求 `http://127.0.0.1:8000` 的本地 `core`
3. Electron 主进程当前只负责窗口、`deep link`、安全凭证存储
4. 代码里没有“启动本地 `core` 进程”的生产逻辑

所以当前真实体验是：

1. 开发者先手动启动 `core`
2. 再启动或安装 Electron 客户端
3. Electron 只是消费已经存在的本地服务

这不是可发布的桌面产品。

---

## 3. 方案对比

### 方案 A：让用户自己装 Python 并手动启动 `core`

不推荐。

问题：

1. 安装链过长，用户体验不可接受
2. 平台差异大，环境问题会淹没业务问题
3. 无法称为“桌面应用发布”

### 方案 B：把 `core` 逻辑直接塞进 Electron 主进程 / Renderer

不推荐。

问题：

1. 破坏当前 `core API/WS contract`
2. UI、任务调度、媒体处理、状态管理会重新耦合
3. 长任务、`SQLite`、素材处理、`agent loop` 会把 Electron 主进程拖重
4. 后续替换底层技术栈成本更高

### 方案 C：保留独立 `core`，但把它作为随安装包分发的本地 service 自动托管

推荐，这是最佳实践方案。

优点：

1. 保留现有 `core` 的边界和契约
2. Electron 只做桌面壳和进程托管
3. `core` 崩溃可单独检测和拉起，稳定性更高
4. 媒体处理、本地状态、`SQLite`、`agent loop` 仍在独立进程里运行
5. 后续把 `core` 从 `Python` 迁到别的实现也不会冲击前端

本文档选择 **方案 C**。

---

## 4. 总体设计

最终交付形态：

```text
安装包
├── Electron App
│   ├── Main Process（主进程）
│   ├── Renderer（前端 UI）
│   └── Preload / IPC
└── Embedded Core Runtime
    ├── core 可执行文件 / Python runtime
    ├── 配套资源
    └── 本地启动脚本（如需要）
```

运行时链路：

```text
用户双击应用
→ Electron Main 启动
→ Main 自动拉起本地 core
→ 轮询 /health
→ core ready
→ Renderer 进入正常工作态
→ 用户使用 chat / ingest / export
→ 退出应用时 Main 关闭 core 子进程
```

---

## 5. 推荐落地路径

### 5.1 总原则

1. `core` 仍是独立本地进程
2. Electron 主进程只负责托管，不承载业务实现
3. 前端继续走 `HTTP / WebSocket`
4. `core` 的开发态和发布态要分开

开发态：

1. 允许继续 `cd core && uvicorn server:app`
2. Electron 开发时可连外部手动启动的 `core`

发布态：

1. Electron 自动拉起打包后的 `core`
2. 用户不感知 `Python`、`uvicorn`、环境变量细节

### 5.2 `core` 产品化形态

推荐优先级：

1. 第一阶段：`PyInstaller` 打成单目录可执行程序
2. 第二阶段：如体积与稳定性可接受，再考虑单文件模式

原因：

1. 单目录模式更稳，调试更容易
2. 对 `ffmpeg-python`、`scenedetect`、`Pillow`、本地资源收集更友好
3. 更适合作为第一版桌面发布链

`core` 的交付物目标应是：

```text
core-dist/
├── entrocut-core(.exe)
├── 依赖动态库 / Python runtime
└── 必要资源
```

### 5.3 Electron 主进程职责

新增一个明确的 `core supervisor（托管器）` 模块，职责只有这些：

1. 解析打包后 `core` 可执行文件路径
2. 选择并占用本地端口
3. `spawn` 子进程
4. 注入运行时环境变量
5. 轮询 `GET /health`
6. 维护 ready / failed / restarting 状态
7. 应用退出时优雅关闭子进程

Electron 主进程不做：

1. 不内嵌 `core` 业务逻辑
2. 不直接处理 `SQLite`
3. 不承接媒体处理

### 5.4 前端职责

前端继续用已有的 `coreClient`，但要加一层“桌面服务准备态”：

1. app 启动后先等待 `core` ready
2. 如果 `core` 未就绪，显示桌面初始化页
3. 如果 `core` 启动失败，展示明确错误和诊断入口

不要让前端自己猜测“连不上 8000 是不是用户没开服务”。  
在桌面发布态里，这应该被解释为：

`本地核心服务启动失败`

---

## 6. 关键模块设计

### 6.1 `core` 打包模块

建议新增：

1. `core/scripts/build_desktop_core.sh`
2. `core/pyinstaller.spec`
3. `core/dist/` 或统一输出到仓库级 `artifacts/`

职责：

1. 固定入口：`server:app`
2. 固定依赖收集
3. 固定输出结构
4. 明确平台相关差异

### 6.2 Electron `core supervisor`

建议新增：

1. `client/main/coreSupervisor.ts`

最小接口：

1. `startCore(): Promise<CoreStartResult>`
2. `waitForCoreReady(): Promise<void>`
3. `stopCore(): Promise<void>`
4. `getCoreStatus(): CoreStatus`

状态枚举建议：

1. `idle`
2. `starting`
3. `ready`
4. `failed`
5. `stopped`

### 6.3 配置与环境变量

桌面发布态必须明确区分：

1. 开发态 `core base url`
2. 发布态 `core base url`

建议策略：

1. Electron 主进程启动 `core` 时动态选定端口
2. 通过 `preload + IPC` 把实际 `core base url` 暴露给 Renderer
3. Renderer 不再硬编码永远使用 `127.0.0.1:8000`

这一步很关键，因为：

1. 避免端口被占用时整包应用直接不可用
2. 避免开发态与发布态配置混淆

### 6.4 数据目录

桌面发布态下，`ENTROCUT_APP_DATA_ROOT` 不能再依赖开发者手工配置。

建议：

1. Electron 主进程使用 `app.getPath("userData")`
2. 在其下创建 `core-data/`
3. 启动 `core` 时注入：
   - `ENTROCUT_APP_DATA_ROOT=<userData>/core-data`
   - `CORE_PORT=<动态端口>`

这样可保证：

1. 每个用户有稳定的数据根目录
2. `SQLite`、项目工作目录、凭证镜像都落在可控路径

---

## 7. 端到端运行时流程

### 7.1 应用启动

1. Electron 主进程启动
2. 解析本地 `core` 可执行文件路径
3. 选择空闲端口，例如 `127.0.0.1:38000`
4. 设置 `ENTROCUT_APP_DATA_ROOT`、`CORE_PORT`
5. `spawn` 本地 `core`
6. 轮询 `GET /health`
7. 成功后把 `core base url` 注入给 Renderer

### 7.2 应用运行中

1. Renderer 继续通过 `HTTP / WebSocket` 调用 `core`
2. Main 持有 `core` 子进程句柄
3. 如果 `core` 异常退出，Main 记录日志并通知前端进入错误态

### 7.3 应用退出

1. Main 发送优雅终止信号
2. 超时后强制结束子进程
3. 确保没有孤儿进程残留

---

## 8. 与主流桌面应用对齐的点

要达到“像主流桌面应用一样下载安装即可使用”，必须满足这几条：

1. 安装包内已经包含完整运行时
2. 用户不需要额外安装语言环境
3. 双击应用即可打开到可用状态
4. 本地服务的启动与关闭是自动的
5. 本地错误能被应用自己解释，而不是暴露命令行细节

对 EntroCut 来说，产品化的关键不在 UI 打包，而在：

`把 core 从开发期的 Python 服务，变成发布期的内置本地能力。`

---

## 9. 分阶段执行计划

### Phase 1：打通最小可用链路

目标：

`Windows 桌面包安装后可自动启动 core，前端能正常连通 core。`

任务：

1. 为 `core` 增加桌面打包脚本
2. 用 `PyInstaller` 产出 Windows 可执行文件
3. Electron 主进程新增 `coreSupervisor`
4. `electron-builder` 通过 `extraResources` 携带 `core`
5. Renderer 改成从 Electron 获取实际 `core base url`
6. 应用启动页增加 `core starting / failed` 状态

### Phase 2：补齐 Linux / macOS

目标：

`三平台具备一致的“安装即用”体验。`

任务：

1. 处理平台差异下的 `spawn` 路径与权限
2. 调整三平台 `PyInstaller` / 打包产物结构
3. 完善 CI，分别构建三平台安装包

### Phase 3：提升桌面韧性

目标：

`桌面端面对异常退出、端口冲突、升级迁移时仍保持可恢复。`

任务：

1. 增加 `core` 崩溃诊断日志
2. 端口冲突自动回退
3. 版本升级时的数据迁移策略
4. 启动失败的错误分级与用户文案

---

## 10. `electron-builder` 改造思路

当前 `electron-builder` 只打包 Electron 前端。  
需要新增：

1. `extraResources`
   - 把不同平台对应的 `core` 二进制放进安装包
2. 平台条件打包
   - Windows 包放 Windows 版 `core`
   - macOS 包放 macOS 版 `core`
   - Linux 包放 Linux 版 `core`

发布链建议改成：

```text
构建前端
→ 构建 Electron main/preload
→ 构建对应平台 core binary
→ electron-builder 打包所有资源
→ 产出桌面安装包
```

而不是只做：

```text
前端 build
→ Electron 打包
```

---

## 11. 风险与缓解

### 风险 1：`core` 打包后依赖缺失

问题：

1. `ffmpeg-python`、`scenedetect`、`Pillow`、本地动态库收集不完整

缓解：

1. 第一阶段优先做单目录打包
2. 为 `core` 增加独立冒烟测试
3. 每个平台单独验证 `health / create_project / ingest`

### 风险 2：Electron 启动时 race condition（竞态）

问题：

1. 前端先请求 `core`
2. 但 `core` 还没 ready

缓解：

1. 由 Main 管 ready gate
2. Renderer 在收到 ready 之前不进入工作台

### 风险 3：端口冲突

问题：

1. `8000` 可能被其他服务占用

缓解：

1. 不在发布态硬编码固定端口
2. 启动时动态分配
3. 运行时把实际地址下发给前端

### 风险 4：孤儿进程

问题：

1. 应用退出后 `core` 没有退出

缓解：

1. Main 保存子进程句柄
2. `before-quit / window-all-closed` 做显式关闭
3. 超时后强制 kill

### 风险 5：把桌面壳做成“只是浏览器包裹”

问题：

1. 最后仍要求用户自己配本地服务

缓解：

1. 把“安装即用”写成硬验收标准
2. 没有自动拉起 `core` 的版本不得称为桌面正式可用版本

---

## 12. 验收标准

满足以下条件，才算桌面一体化发布达标：

1. 全新机器上不安装 Python，也能安装并打开 EntroCut
2. 双击桌面应用后，`core` 自动启动
3. 前端无需手工配置 `core` 地址
4. 首次打开可以成功通过 `health`
5. 可以完成：
   - 创建项目
   - 导入素材
   - 发送 chat
   - 导出
6. 关闭应用后没有残留 `core` 进程
7. 启动失败时，用户看到的是产品级错误提示，而不是命令行堆栈

---

## 13. 明确非目标

当前方案先不做这些事：

1. 不把 `core` 迁移到 `Rust / Go`
2. 不引入自动更新系统
3. 不引入多实例 `core` 管理
4. 不在第一阶段做复杂守护重启策略
5. 不在第一阶段解决所有三平台媒体库兼容问题

---

## 14. 推荐的第一步

如果要最稳地推进，这件事不要一口吃成“三平台发布系统”，而应该先收口成一个明确目标：

`先做 Windows First 的桌面一体化 MVP：Electron 安装包内置 core，应用启动时自动拉起并探活。`

原因：

1. 当前你本机开发环境就在 Windows / WSL 附近
2. 可以最快验证“桌面壳 + 本地 core service”这条产品路线是否跑通
3. 一旦 Windows 跑通，Linux / macOS 主要是工程打包问题，而不是架构问题

---

## 15. 结论

EntroCut 当前缺的不是 Electron 打包本身，而是：

`把 core 从开发者手动启动的 Python 服务，变成桌面应用自动托管的本地能力。`

最佳实践不是让用户自己装环境，也不是把 `core` 塞回 Electron，而是：

`保留 core 为独立本地服务进程，并把它随安装包分发，由 Electron Main 自动启动、探活、关闭。

## 16. 团队防冲突开发公约与并行护栏（工程师 B 必读）

本项目当前由三位工程师并行推进，请在开发时严格遵守以下边界，避免产生代码冲突：

1. **你的专属领域**：Core 的打包脚本（`build_desktop_core.sh`, `pyinstaller.spec`）、Electron 主进程的托管逻辑（`coreSupervisor.ts`）以及应用的启动生命周期。
2. **核心公共文件 `client/main/main.ts`**：你负责在此注入 Core 的启动与托管逻辑。负责真实 Ingest 的工程师 C 会在此注册目录扫描的 IPC Handler。**约定**：你们应将各自的核心逻辑封装在独立文件（如 `coreSupervisor.ts` 和 `fileScanner.ts`）中，在 `main.ts` 中仅作单行注册，避免主文件冲突。
3. **前端网络层**：你需要在应用启动页增加全局 Loading 态，并动态将实际的 Core Base URL 暴露给 Renderer。内部的具体业务请求逻辑（如创建项目、聊天、预览）由工程师 A 和 C 填充，你无需关注。`

这条路线最符合当前架构，也最接近主流桌面应用的真实交付方式。
