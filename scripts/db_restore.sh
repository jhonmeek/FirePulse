#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <path-to-firepulse.dump>" >&2
  exit 1
fi

DUMP_PATH="$1"
if [ ! -f "${DUMP_PATH}" ]; then
  echo "Backup file not found: ${DUMP_PATH}" >&2
  exit 1
fi

if [ -f "${DUMP_PATH}.sha256" ]; then
  echo "[1/3] Verifying SHA-256 checksum..."
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "${DUMP_PATH}.sha256"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c "${DUMP_PATH}.sha256"
  fi
fi

echo "[2/3] Restoring PostGIS dump into db container..."
docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "${DUMP_PATH}"

echo "[3/3] Verifying /api/v1/health/..."
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/').read().decode())"
