# 2026-04-08 Electron 打包、GitHub Actions CI 与发版流程配置

## 背景

EntroCut client 是一个 Electron 桌面应用（Electron + React + Vite + Zustand），之前只有开发模式，没有打包和分发能力。本次工作的目标是为 client 配置完整的打包链路，实现推送 tag 后自动构建三平台安装包并发布到 GitHub Releases。

## 做了什么

### 1. electron-builder 配置

- 新增 `client/electron-builder.yml`：声明 appId、三平台产物目标（NSIS/DMG+ZIP/AppImage+DEB）、deep link 协议注册、产物命名规则、GitHub 发布配置
- `client/package.json` 新增 `author`/`description`/`homepage` 字段（DEB 构建对 maintainer 信息的强制要求）
- 新增构建 scripts：`electron:build-all`、`electron:build:win`、`electron:build:mac`、`electron:build:linux`
- 从 `client/public/icon.svg` 生成 `client/build/icon.png`（512x512），作为应用图标

### 2. GitHub Actions CI 流水线

新增 `.github/workflows/client-build.yml`：
- 触发条件：`v*` tag push 或手动触发
- 三平台矩阵并行构建（windows-latest / macos-latest / ubuntu-latest）
- 产物通过 upload-artifact 上传，同时 electron-builder 自动发布到 GitHub Releases

### 3. .gitignore 更新

- 新增 `**/release/`：排除 electron-builder 本地打包产物
- 新增 `*:Zone.Identifier`：排除 Windows Zone.Identifier 文件（文件名含冒号，Windows 文件系统非法）

### 4. 发版流程文档

新增 `docs/client/01_electron_build_and_release.md`，覆盖打包配置说明、本地构建、CI 流水线、标准发版步骤、版本号规范、图标管理和故障排查。

## 踩过的坑

### Zone.Identifier 导致 Windows checkout 失败

**现象**：GitHub Actions Windows runner 执行 `git checkout` 时报 `error: invalid path`，文件名含冒号 `:`。

**原因**：6 个 `docs/毕设/` 下的 `*.pptx:Zone.Identifier` / `*.pdf:Zone.Identifier` 文件被提交到仓库。这些是 macOS 的扩展属性文件，文件名含冒号，NTFS 不允许。

**解决**：`git rm --cached` 移除这些文件，`.gitignore` 新增 `*:Zone.Identifier` 规则。

### npm ci 跨平台 rollup 原生依赖缺失

**现象**：macOS runner 执行 `tsc -b && vite build` 时报 `Cannot find module @rollup/rollup-darwin-arm64`。

**原因**：`package-lock.json` 在 Linux 生成，锁定了 `@rollup/rollup-linux-x64-gnu`。`npm ci` 严格按 lockfile 安装，不会解析其他平台的 optional dependencies。

**解决**：CI 中安装依赖前用 node 脚本删除 `package-lock.json`，改用 `npm install` 让每个平台 runner 自行解析原生依赖。同时移除 npm cache 配置，因为 lockfile 不再参与 CI。

### Node.js 版本过低

**现象**：`@electron/rebuild` 要求 Node >= 22.12.0，CI 初始配置使用 Node 20。

**解决**：升级到 Node 22。

### GITHUB_TOKEN 权限不足

**现象**：三平台打包全部成功，但 electron-builder 调用 GitHub API 创建 Release 时返回 403 `Resource not accessible by integration`。

**原因**：tag 触发的 workflow 中，`GITHUB_TOKEN` 默认没有 `contents:write` 权限。

**解决**：在 workflow 文件中显式声明 `permissions: contents: write`。

## 最终 CI 配置关键点

```yaml
permissions:
  contents: write          # 允许创建 Release

jobs:
  build:
    strategy:
      matrix:              # 三平台并行
        include:
          - os: windows-latest
          - os: macos-latest
          - os: ubuntu-latest

    steps:
      - node-version: 22   # 满足 @electron/rebuild 要求
      - 删除 lockfile       # 解决跨平台原生依赖
      - npm install
      - electron-builder    # 打包 + 发布
```

## 发版流程

```bash
# 1. 改版本号（client/package.json version 字段）
# 2. 提交
git commit -m "chore: bump version to x.y.z"
# 3. 打 tag
git tag vx.y.z
# 4. 推送
git push && git push --tags
# 5. CI 自动构建 + 发布到 GitHub Releases
```

## 当前状态

三平台构建 + GitHub Releases 发布已完整跑通（验证 tag `v0.1.0-test`）。待合并到 main 分支后即可正式发版。

产物清单：
- Windows: `entrocut-client-0.1.0-setup.exe`（NSIS 安装器）
- macOS: `EntroCut-0.1.0-arm64.dmg` + `EntroCut-0.1.0-arm64-mac.zip`
- Linux: `entrocut-client-0.1.0.AppImage` + `entrocut-client-0.1.0.deb`

## 后续可选迭代

1. macOS 签名 + 公证（Apple Developer 证书）
2. Windows 代码签名证书
3. `electron-updater` 自动更新
4. `release-please` 自动版本号管理
