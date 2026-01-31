# 1. 核心工具链安装 (Core Toolchain)

在开始代码编写前，请确保本地已安装以下基础软件：

- **Node.js (20.x+)**: 用于 Electron 和 React 前端。推荐使用 `fnm` 或 `nvm` 管理版本。
- **Python (3.10+)**: 用于算法 Sidecar 和 FastAPI 后端。
- **FFmpeg**: 必须安装并配置到系统环境变量 `PATH` 中（本地切分与抽帧的核心）。
    - *验证方法*: 在终端输入 `ffmpeg -version`。

# 2. Monorepo 目录初始化 (Environment Setup)

在根目录下按照以下步骤初始化环境，以便coding agent能够理解全局上下文：

本指南详细记录了项目启动阶段的目录创建、环境初始化及基础架构配置。

## 1. 创建项目根目录与基础结构

首先创建 Monorepo 结构的根文件夹。

```
# 创建并进入根目录
mkdir Entrocut && cd Entrocu

# 创建三个核心子目录
mkdir client core server docs

```

## 2. 初始化本地算法内核 (core)

这里存放 Python Sidecar，负责视频切分和本地抽帧。

```
cd core
# 创建虚拟环境
python -m venv venv

# 激活环境 (Windows WSL2 Ubuntu)
source venv/bin/activate

# 安装核心依赖
pip install scenedetect[opencv] ffmpeg-python dashscope dashvector

# 创建基础文件结构
mkdir detect process
touch server.py .env.example
cd ..

```

## 3. 初始化云端后端 (server)

这里存放 FastAPI 业务逻辑，负责与 MongoDB 和阿里云交互。

```
cd server
# 创建虚拟环境
python -m venv venv

# 激活环境 (Windows WSL2 Ubuntu)
source venv/bin/activate

# 安装核心依赖
pip install fastapi uvicorn motor pydantic python-dotenv

# 创建基础文件结构
mkdir models routes utils
touch main.py .env.example
cd ..

```

## 4. 初始化客户端应用 (client)

这里是 Electron 桌面端和 React 前端。推荐使用 Vite 快速搭建。

> 工具说明：为什么选择 Vite？
Vite 是目前前端最流行的构建工具，相比传统的 Webpack，它在开发阶段利用浏览器原生 ESM 特性实现秒级启动和热更新。常见的替代方案还包括 Rspack (Rust 编写，高性能 Webpack 兼容) 和 Webpack (生态最成熟但配置较重)。
> 

```
cd client

# 使用 Vite 初始化 React + TS 项目 (直接安装在当前目录)
npm create vite@latest . -- --template react-ts

# 安装基础依赖
npm install

# 安装项目选定的核心依赖
npm install electron lucide-react @tanstack/react-query axios
npm install -D electron-builder wait-on concurrently

# 创建 Electron 主进程目录
mkdir main
touch main/main.ts main/preload.ts main/sidecar.ts

# 创建本地数据库与类型定义
mkdir src/db src/types
cd ..

```

## 5. 配置全局环境变量模板

在根目录下创建一个统一的模板，方便团队成员协作。

```
# 回到根目录创建全局配置文件
touch .gitignore .env.example

# 写入基本的 .gitignore
echo "node_modules/
venv/
__pycache__/
*.db
.env
dist/
build/" > .gitignore

```

## 6. 使用 coding agent 快速生成初始代码

现在你已经搭建好了骨架，可以利用coding agent在根目录下运行以下指令，让它帮你填充基础代码：

> "Claude, I have created the directory structure. Please:
> 
> 1. Generate a basic FastAPI 'Hello World' in `server/main.py`.
> 2. Generate a basic Electron entry point in `client/main/main.ts`.
> 3. Create a simple Python script in `core/server.py` that starts a Flask or FastAPI server on port 8000 for the Sidecar."

## 7. 最终目录预览

执行完以上命令后，你的项目结构应如下所示：

```
video-retrieval-app/
├── client/              # Electron + React (前端与桌面壳)
│   ├── main/            # Electron 主进程逻辑
│   ├── src/             # React 渲染进程界面
│   └── package.json
├── core/                # 本地算法 Sidecar (Python)
│   ├── venv/            # 算法独立环境
│   ├── detect/          # PySceneDetect 逻辑
│   └── server.py        # 本地算法服务入口
├── server/              # 云端后端 (FastAPI)
│   ├── venv/            # 后端独立环境
│   ├── models/          # MongoDB 模型
│   └── main.py          # 业务 API 入口
├── docs/                # 项目文档与 Schema
└── .gitignore

```

## 8. 调试启动建议

在开发阶段，你需要同时运行三个进程。建议在 VSCode 中创建 `tasks.json` 或在根目录写一个简单的 `dev.sh`：

- **终端 1**: `cd server && source venv/bin/activate && uvicorn main:app --reload` (云端服务)
- **终端 2**: `cd core && source venv/bin/activate && python server.py` (本地算法服务)
- **终端 3**: `cd client && npm run dev` (Electron 界面)

# 3. VSCode 插件推荐 (Optimizing VSCode)

为了提升多语言协作体验，请安装以下扩展：

1. **Python (Microsoft)**: 提供代码补全、调试及虚拟环境切换。
2. **ESLint & Prettier**: 保持前端代码风格一致。
3. **Tailwind CSS IntelliSense**: 用于快速编写渲染进程的样式。
4. **SQLite Viewer**: 方便在 VSCode 内直接查看本地 `SQLite` 数据库内容。
5. **REST Client**: 在不启动前端的情况下测试 FastAPI 接口。

# 4. 本地联调方案 (Local Debugging)

由于项目包含多个进程，建议配置 VSCode 的 `launch.json` 实现多目标调试：

- **调试目标 1**: Electron Main Process (Node.js)
- **调试目标 2**: FastAPI Server (Python)
- **调试目标 3**: Python Sidecar (独立运行测试)

在开发阶段，你可以保持 **FastAPI** 和 **DashVector** 在线，而将 **Python Sidecar** 运行在本地调试模式。

# 5. 配置文件管理细节

1. **Git 忽略**: 确保 `.gitignore` 包含所有 `venv/`, `node_modules/`, `dist/`, `.log`, `.env` 以及 SQLite 的 `.db` 文件。
2. **环境变量**: 在项目根目录创建 `.env.example`。当成员使用 Claude Code 时，可以要求：
    
    > "Help me fill in the .env file based on the template, I'll provide the API keys separately."
    > 

# 7. 确认清单 (Pre-flight Check)

执行 `ffmpeg -version` 有正确输出。

`client`, `core`, `server` 三个目录的依赖均已隔离安装。

已在 VSCode 中选择了正确的 Python 解析器（venv 环境）。