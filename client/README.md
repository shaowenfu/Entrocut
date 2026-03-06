# Client Shell

`client` 当前是最小 `UI Shell（界面壳层）`，用于承载后续 `AI-first（AI 优先）` 交互重构。

## 当前能力

1. React + Vite 页面壳层可启动。
2. Electron 主进程文件仅占位，不包含旧 `IPC` 与 `Sidecar` 逻辑。
3. `electron:dev` 已接通，支持 `Vite + Electron` 联动本地调试。
4. 请求默认透传 `Authorization` 与 `X-Request-ID`。

## 非目标

1. 不包含历史任务流 UI。
2. 不包含历史 SQLite 与轮询状态逻辑。
