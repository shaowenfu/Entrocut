# EntroCut Client 打包与发版流程

## 一、整体架构

```
本地开发 → 提交代码 → git tag → GitHub Actions 自动构建 → GitHub Releases 发布
                                                    ↓
                                          用户从 Releases 下载安装
```

涉及的核心文件：

| 文件 | 职责 |
|---|---|
| `client/electron-builder.yml` | electron-builder 打包配置 |
| `client/package.json` | 版本号 + 构建 scripts |
| `client/build/icon.png` | 应用图标（512x512，builder 自动生成 ICO/ICNS） |
| `.github/workflows/client-build.yml` | CI 自动构建流水线 |

## 二、打包配置说明

### electron-builder.yml 关键字段

```yaml
appId: com.entrocut.desktop          # 应用唯一标识，macOS/iOS 生态用
productName: EntroCut                # 安装包显示名称
directories.output: release          # 产物输出到 client/release/
directories.buildResources: build    # 图标等资源在 client/build/

files:                               # 打包进安装包的文件
  - dist/**/*                        #   Vite 渲染层产物
  - dist-electron/**/*               #   esbuild 主进程产物
  - package.json
  - "!node_modules/**/*"             #   排除 node_modules

extraMetadata.main: dist-electron/main.js  # 覆盖 main 入口指向编译产物
```

### 三平台产物

| 平台 | 产物格式 | 文件名模式 |
|---|---|---|
| Windows | NSIS 安装器（`.exe`） | `entrocut-client-{version}-setup.exe` |
| macOS | DMG + ZIP | `EntroCut-{version}.dmg` / `.zip` |
| Linux | AppImage + DEB | `entrocut-client-{version}.AppImage` / `.deb` |

### Deep Link 协议

macOS 通过 `CFBundleURLSchemes` 注册 `entrocut://` 协议，用于 OAuth 回调。
Windows 上 NSIS 安装器会自动处理协议注册（electron-builder 内置）。

## 三、本地构建

### 前置条件

- Node.js 20+
- `client/package-lock.json` 存在（首次需 `npm install` 生成）

### 构建当前平台

```bash
cd client
npm run electron:build-all
```

### 构建指定平台

```bash
npm run electron:build:win     # Windows
npm run electron:build:mac     # macOS
npm run electron:build:linux   # Linux
```

产物在 `client/release/` 下。

> **注意**：跨平台构建有限制。macOS 上可以构建 macOS + Linux；Windows 上只能构建 Windows。如需全平台产物，依赖 GitHub Actions 矩阵构建。

### 构建链路

每个 `electron:build:*` script 依次执行：

```
npm run build              # tsc 类型检查 + Vite 编译渲染层 → dist/
npm run electron:build-main # esbuild 编译主进程 → dist-electron/
electron-builder --{platform}  # 读取 electron-builder.yml → 产出安装包到 release/
```

## 四、GitHub Actions 自动构建

### 触发条件

1. **Tag push**：推送 `v*` 格式的 tag（如 `v0.1.0`）
2. **手动触发**：GitHub Actions 页面点击 "Run workflow"

### 流水线行为

```
┌─ windows-latest ──→ npm run electron:build:win  ──→ .exe
│
├─ macos-latest  ───→ npm run electron:build:mac  ──→ .dmg + .zip
│
└─ ubuntu-latest ───→ npm run electron:build:linux ──→ .AppImage + .deb
```

三个 job 并行执行，产物通过 `upload-artifact` 上传到 GitHub Actions Artifacts，
同时 `electron-builder` 通过 `GH_TOKEN` 自动创建 GitHub Release 并上传安装包。

### GitHub Repo 权限配置

CI 使用内置 `GITHUB_TOKEN`，需要确保有写入权限：

1. 进入 repo → Settings → Actions → General
2. "Workflow permissions" 选择 **"Read and write permissions"**
3. 保存

如果不配置，构建可以完成但无法创建 Release。

## 五、发版流程

### 标准发版步骤

```bash
# 1. 确认在 main 分支，代码已合并
git checkout main
git pull origin main

# 2. 修改版本号
#    编辑 client/package.json 中的 version 字段
#    例：0.1.0 → 0.2.0

# 3. 提交版本变更
git add client/package.json
git commit -m "chore: bump client version to x.y.z"

# 4. 打 tag（版本号必须与 package.json 一致）
git tag vx.y.z

# 5. 推送 commit 和 tag
git push origin main
git push origin vx.y.z
```

推送 tag 后 GitHub Actions 自动触发，约 10-15 分钟后可在 GitHub Releases 页面看到产物。

### 验证构建结果

1. 进入 repo → Actions 标签页，查看 `client-build` workflow 运行状态
2. 构建成功后进入 Releases 标签页，确认安装包已上传
3. 下载对应平台安装包，本地安装验证

### 回退与重发

如果构建失败需要重发：

```bash
# 删除远程 tag
git push origin :refs/tags/vx.y.z

# 修复问题后重新打 tag
git tag vx.y.z
git push origin vx.y.z
```

如果需要手动删除 GitHub Release，在 Releases 页面操作即可。

## 六、版本号规范

采用 Semantic Versioning（语义化版本）：

```
MAJOR.MINOR.PATCH

MAJOR: 不兼容的 API 变更
MINOR: 向后兼容的新功能
PATCH: 向后兼容的问题修复
```

当前阶段（MVP），建议：

- 破坏性变更 → `0.x.0`
- 新功能 → `0.x.y`（MINOR 递增）
- Bug 修复 → `0.x.y`（PATCH 递增）

在 `0.x.x` 阶段，不引入 prerelease 标记（如 `-beta`、`-rc`），保持简单。

## 七、图标管理

当前图标来源：`client/public/icon.svg` → 转换为 `client/build/icon.png`（512x512）。

`electron-builder` 在构建时自动从 `icon.png` 派生：

- Windows：`icon.ico`
- macOS：`icon.icns`
- Linux：直接使用 `icon.png`

如需更换图标，替换 `client/build/icon.png` 即可，建议保持 512x512 或 1024x1024。

正式发布时建议请设计师产出专业图标，包含完整的多尺寸 PNG。

## 八、当前非目标

以下内容当前不涉及，后续按需引入：

1. **代码签名**：macOS 签名 + 公证（notarization）、Windows 代码签名证书
2. **自动更新**：`electron-updater` + 后台检测新版本并提示
3. **自动版本号 bump**：`standard-version` / `release-please` 等 conventional commits 工具
4. **Beta/Canary 通道**：多分发通道管理

## 九、故障排查

### CI 构建失败

| 现象 | 原因 | 解决 |
|---|---|---|
| `npm ci` 报错找不到 lockfile | `package-lock.json` 未提交 | 在 `client/` 下 `npm install` 后提交 lockfile |
| Release 创建失败 403 | `GITHUB_TOKEN` 无写入权限 | 配置 repo Settings → Actions → Write permissions |
| macOS 构建报签名错误 | 未配置 Apple Developer 证书 | MVP 阶段跳过签名，或配置 `CSC_*` secrets |
|产物为空 | `files` 路径匹配失败 | 检查 `dist/` 和 `dist-electron/` 是否在构建时正常生成 |

### 本地构建失败

| 现象 | 原因 | 解决 |
|---|---|---|
| `tsc -b` 报类型错误 | TypeScript 类型不匹配 | 先 `npm run typecheck` 排查 |
| `electron-builder` 找不到入口 | `extraMetadata.main` 配置错误 | 确认 `dist-electron/main.js` 存在 |
| 图标缺失报错 | `build/icon.png` 不存在 | 确认 `client/build/icon.png` 存在 |
