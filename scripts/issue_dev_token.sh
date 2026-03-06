#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_ID="${1:-dev_user_001}"
SECRET="${AUTH_JWT_SECRET:-entrocut-dev-secret-change-me}"
TTL_HOURS="${AUTH_TOKEN_TTL_HOURS:-24}"
export USER_ID SECRET TTL_HOURS

cd "${ROOT_DIR}/server"
source venv/bin/activate

python - <<'PY'
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

user_id = os.environ["USER_ID"]
secret = os.environ["SECRET"]
ttl_hours = int(os.environ["TTL_HOURS"])
now = datetime.now(tz=timezone.utc)
payload = {
    "sub": user_id,
    "iat": int(now.timestamp()),
    "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
    "jti": f"tok_{uuid4().hex[:12]}",
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
PY
