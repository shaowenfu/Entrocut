#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

(
  cd "${ROOT_DIR}/core"
  source venv/bin/activate
  python -m unittest discover -s tests -p 'test_*.py'
)

(
  cd "${ROOT_DIR}/server"
  source venv/bin/activate
  python -m unittest discover -s tests -p 'test_*.py'
)

(
  cd "${ROOT_DIR}/client"
  npm run typecheck
)

bash "${ROOT_DIR}/scripts/phase45_prompt_queue_last_only_check.sh"

echo "Unit and regression tests passed."
