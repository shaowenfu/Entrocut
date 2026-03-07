# EntroCut overview
- Purpose: MVP monorepo for Chat-to-Cut video editing workflow.
- Main services: `client/` (Electron + React UI), `core/` (local FastAPI sidecar for ingest/render/project state), `server/` (cloud FastAPI orchestration for chat/index).
- Current baseline: JWT auth, ErrorEnvelope, Redis-backed jobs, SQLite persistence, request_id propagation.
- Important docs: `README.md`, `PHASE45_DEEP_TASK_AUDIT_AND_TASKLIST.md`, `PHASE45_GIT_COLLAB_PROTOCOL.md`.
- Current collaboration constraint: shared git workspace with engineer-specific file boundaries; avoid touching frozen contracts, client/core business logic, or reserved entrypoints unless explicitly authorized.