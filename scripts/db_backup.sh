#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-data/backups}"
STAMP="$(date -u +%Y%m%d_%H%M%SZ)"
DUMP_PATH="${BACKUP_DIR}/firepulse_${STAMP}.dump"
SNAPSHOT_DIR="${BACKUP_DIR}/demo_snapshot"

mkdir -p "${BACKUP_DIR}"

echo "[1/3] Creating PostGIS custom-format backup: ${DUMP_PATH}"
docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "${DUMP_PATH}"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${DUMP_PATH}" > "${DUMP_PATH}.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${DUMP_PATH}" > "${DUMP_PATH}.sha256"
fi

echo "[2/3] Exporting offline JSON demo snapshot: ${SNAPSHOT_DIR}"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose exec -T backend python manage.py export_demo_snapshot --output "/data/backups/demo_snapshot"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose exec -T backend python manage.py export_demo_snapshot --output "/data/backups/demo_snapshot" --verify

echo "[3/3] Done. Backup size: $(wc -c < "${DUMP_PATH}") bytes"
