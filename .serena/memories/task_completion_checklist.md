# Task completion checklist
- Run `git status --short` before editing; if unrelated dirty files exist outside your boundary, do not modify them.
- Keep modifications inside the assigned file boundary.
- After changes, run task-specific validation plus at least one smoke command when relevant.
- Before finishing, run `git diff --stat` and `git status --short` and confirm only your files are included.
- In this repo, many tests require local `core/server/client` processes and Redis; when sandboxed network blocks localhost, re-run those commands with escalation.