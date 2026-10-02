#!/usr/bin/env bash
# Wait for Postgres, apply migrations, then exec the container command.
set -euo pipefail

python - <<'PY'
import asyncio
import os
import sys

import asyncpg

url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


async def wait() -> None:
    deadline = 60
    for attempt in range(deadline):
        try:
            connection = await asyncpg.connect(url)
        except Exception as exc:  # noqa: BLE001 - any connect failure is retryable here
            if attempt == deadline - 1:
                print(f"database unreachable after {deadline}s: {exc}", file=sys.stderr)
                raise
            await asyncio.sleep(1)
        else:
            await connection.close()
            print("database is ready")
            return


asyncio.run(wait())
PY

echo "applying migrations"
alembic upgrade head

exec "$@"
