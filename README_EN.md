# EntroCut

[English](README_EN.md) | [简体中文](README.md)

`EntroCut` is an early-stage `Chat-to-Cut` open-source exploration project. It attempts to advance video editing from "manual timeline operation" to "using natural language to continuously converge editing drafts":

```text
intent
  -> retrieve (find material)
  -> inspect (judge candidates)
  -> patch (modify draft)
  -> preview/export
```

The project is not yet a mature product, nor a replacement for general video editing software. More accurately, it is an `editing agent` prototype system taking shape: it has completed the basic closed-loop of desktop client, local `core`, and cloud `server`, but the `planner` decision quality, long-chain stability, footage understanding performance, and product experience are still continuously being polished.

## Project Vision

The core of video editing is not dragging the timeline itself, but selecting, sorting, trimming, and organizing a viewing sequence from raw footage that can express the intent.

The long-term vision of `EntroCut` is:

> Let users use natural language to gradually converge vague editing goals into an executable, previewable, and modifiable `EditDraft`.

This means the project does not focus on "directly generating a final masterpiece with one sentence," but on `iterative convergence`:

1. The user expresses the goal.
2. The system establishes a structured `EditDraft`.
3. The `agent loop` calls tools based on context.
4. The user continues to correct through preview, feedback, and localized selection.
5. Finally, exports a playable video result.

## Current Development Status

The current repository has formed a three-end structure:

- `client/`: Desktop frontend, based on `Electron + React + Vite + Zustand`.
- `core/`: Local backend, based on `FastAPI + SQLite + ffmpeg`, maintaining local projects, footage import, `EditDraft`, preview, and export.
- `server/`: Cloud capability gateway, based on `FastAPI`, providing authentication, `chat proxy`, vectorization, retrieval, and visual inspect capabilities.

Already clearly defined parts:
1. The minimum closed-loop of `Launchpad -> Workspace -> import -> chat -> preview/export` has been established.
2. `EditDraft` has become the core source of truth; `storyboard` is only a UI derived view.
3. `core` has advanced from a pure prototype state to a `SQLite-backed local backend`.
4. `server` already has main-chain capabilities like `Google/GitHub OAuth`, `JWT`, `OpenAI-compatible chat proxy`, `vectorize/retrieval/inspect`.
5. The desktop client can now host the local `core` process and access local media capabilities via `Electron IPC`.

Parts still being finalized:
1. The decision-making quality and multi-turn stability of the `planner` still need continuous optimization.
2. The `retrieve / inspect / patch / preview` toolchain is connected, but end-to-end performance requires more real-world footage validation.
3. `preview/export` has real rendering outputs, but encoding parameters, performance, audio, and failure recovery are not yet in their final production form.
4. `credits / BYOK / provider compatibility` still need more systematic regression.
5. Project documentation is transitioning from development notes to more stable open-source entry points.

## Three-port README Navigation

For more detailed engineering status, please directly refer to the sub-directory READMEs:

| Module | Description | Document |
| --- | --- | --- |
| `client/` | Desktop frontend, project entry, workbench, Electron local capability bridge | [client/README.md](./client/README.md) |
| `core/` | Local project source of truth, footage import, agent loop, preview/export | [core/README.md](./core/README.md) |
| `server/` | Cloud authentication, model gateway, vector retrieval, visual inspect | [server/README.md](./server/README.md) |

## Current Project Structure

The root directory only keeps high-level navigation; for the internal file structure of each end, please refer to the corresponding README.

```text
Entrocut/
├── client/                       # Electron + React desktop frontend
├── core/                         # Local FastAPI backend and editing source of truth
├── server/                       # Cloud FastAPI capability gateway
├── docs/                         # Design docs, development logs, task descriptions
├── scripts/                      # Repository-level startup, smoke, staging auxiliary scripts
├── logs/                         # Local execution logs
├── temp/                         # Temporary files and short-lived artifacts
├── docker-compose.production.yml # server production deployment orchestration entry
└── README.md                     # Main project entry
```

Common generated artifacts are not core source code: `client/dist/`, `client/dist-electron/`, `client/release/`, `client/node_modules/`, `core/dist/`, `core/build/`, `core/venv/`, `server/venv/`.

## Technology Stack

| Layer | Technology |
| --- | --- |
| Desktop UI | `Electron`, `React`, `Vite`, `TypeScript`, `Zustand` |
| Local Core | `Python`, `FastAPI`, `SQLite`, `WebSocket`, `ffmpeg`, `SceneDetect` |
| Cloud Server | `Python`, `FastAPI`, `MongoDB`, `Redis`, `DashScope`, `DashVector`, `Gemini/OpenAI-compatible API` |
| Packaging | `electron-builder`, `PyInstaller` |

## Local Setup

Simplest method:

```bash
./scripts/dev_up.sh
```

When starting manually, it is recommended to open three separate terminals.

### client

```bash
cd client
npm install
npm run dev -- --host 127.0.0.1 --port 5173
npm run electron:dev
```

### core

```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### server

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## Recommended Reading Path

If you are new to the project, this order is recommended:

1. [client/README.md](./client/README.md): First, understand the desktop entry and user workflow.
2. [core/README.md](./core/README.md): Next, understand the local source of truth, footage import, `EditDraft`, and rendering loop.
3. [server/README.md](./server/README.md): Finally, understand cloud authentication, model proxies, retrieval, and inspect.
4. [docs/README.md](./docs/README.md): When you need deeper design insights, enter the complete document index.
5. [docs/editing/01_edit_draft_schema.md](./docs/editing/01_edit_draft_schema.md): Understand the core data model of `EditDraft`.
6. [docs/agent_runtime/README.md](./docs/agent_runtime/README.md): Understand the planning, tools, context, and execution loop of the `agent runtime`.

## Current Non-goals

To control the complexity of the early-stage project, we explicitly do NOT do the following for now:

1. No comprehensive traditional `timeline editor`.
2. Do not pursue replacing professional human editors in one step.
3. Do not treat `storyboard` as the source of truth; the source of truth remains `EditDraft`.
4. Do not save cloud refresh tokens or third-party secret keys in the local `core`.
5. No promise that current `mock` or `placeholder_first_cut` represents final editing quality.
6. No promise that packaging, billing, BYOK, and provider compatibility have reached production level.

## Open Source Status

This is an early-stage project suitable for developers interested in system design, `agent workflow`, video understanding, desktop local backends, and `LLM tool use` to read and experiment.

Current more appropriate ways to participate:

1. Read the READMEs of the three ends to confirm system boundaries.
2. Use real short video footage to run through the local closed loop.
3. Propose reproducible issues regarding `planner`, `retrieval`, `inspect`, and `preview/export`.
4. Prioritize adding tests, error semantics, and documentation over prematurely stacking new features.

The repository has not yet declared a stable version number or official `LICENSE`. Before using it for production, commercial purposes, or secondary distribution, please verify licenses and dependency authorizations.
