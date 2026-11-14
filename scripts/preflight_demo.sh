#!/usr/bin/env bash
set -euo pipefail

dexec() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose exec -T "$@"
}

SNAPSHOT_CONTAINER_DIR="${1:-/data/backups/demo_snapshot}"
CALIBRATION_CSV="/data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv"

echo "=== FirePulse Preflight Demo Check (H42-H48) ==="

echo "[1/7] Checking Docker containers (db, backend)..."
for svc in firepulse_db firepulse_backend; do
  status="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "${svc}" 2>/dev/null || true)"
  if [ -z "${status}" ]; then
    echo "FAIL: container ${svc} is not running." >&2
    exit 1
  fi
  echo "  OK ${svc}: ${status}"
done

echo "[2/7] Running Django check and migration consistency check..."
dexec backend python manage.py check --fail-level ERROR >/dev/null
dexec backend python manage.py makemigrations --check --dry-run >/dev/null
echo "  OK Django check & migrations clean."

echo "[3/7] Verifying offline demo snapshot manifest & SHA-256..."
dexec backend python manage.py export_demo_snapshot --output "${SNAPSHOT_CONTAINER_DIR}" --verify

echo "[4/7] Verifying M1 calibration CSV backup (if present)..."
if [ -f "data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv" ]; then
  dexec backend python manage.py export_calibration_series --output "${CALIBRATION_CSV}" --verify
else
  echo "  SKIP: data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv not present locally."
fi

echo "[5/7] Checking /api/v1/health/ & fallback readiness..."
dexec backend python -c '
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8000/api/v1/health/")
with urllib.request.urlopen(req, timeout=10) as resp:
    assert resp.status == 200, f"unexpected status {resp.status}"
    fb = resp.headers.get("X-FirePulse-Fallback")
    assert fb == "ready", f"X-FirePulse-Fallback={fb!r}, expected ready"
    data = json.loads(resp.read().decode("utf-8"))
assert data["status"] == "ok", data
assert data["database"] == "connected", data
counts = data["counts"]
assert counts["regions"] == 10, counts
assert counts["hotspots"] >= 292589, counts
assert counts["grid_cell_months"] >= 42482, counts
assert counts["harmonized_months"] >= 6011, counts
print("  OK health:", json.dumps(counts), "| fallback:", fb)
'

echo "[6/7] Smoke-testing API endpoints used by MapLibre, ECharts, Calendar, Methodology & Export..."
dexec backend python -c '
import json, urllib.request
checks = [
    ("regions", "/api/v1/regions/?include_geom=false", "application/json"),
    ("coverage", "/api/v1/coverage/?region=GA", "application/json"),
    ("calendar", "/api/v1/calendar/?region=GA&start=2001-01&end=2025-12&filter_static=true", "application/json"),
    ("anomalies", "/api/v1/anomalies/?region=GA&start=2001-01&end=2025-12&filter_static=true&top_n=5", "application/json"),
    ("hotspots", "/api/v1/hotspots/?region=GA&start=2001-01&end=2025-12&filter_static=true&mode=grid&agg=cell&include_static_cells=true&limit=5000", "application/json"),
    ("methodology", "/api/v1/methodology/?region=GA&filter_static=true", "application/json"),
    ("bbox_calendar", "/api/v1/calendar/?bbox=10.5,-3.0,12.5,-1.0&start=2024-06&end=2024-09", "application/json"),
    ("export_csv", "/api/v1/export/?dataset=series&region=GA&start=2001-01&end=2025-12&filter_static=true", "text/csv"),
]
for label, path, expected_ct in checks:
    with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=15) as resp:
        assert resp.status == 200, f"{label}: HTTP {resp.status}"
        ct = resp.headers.get("Content-Type", "")
        assert expected_ct in ct, f"{label}: Content-Type {ct!r}"
        body = resp.read().decode("utf-8")
        if expected_ct == "application/json":
            parsed = json.loads(body)
            if label == "hotspots":
                assert len(parsed.get("features", [])) > 0, "hotspots returned 0 features"
        else:
            lines = [ln for ln in body.splitlines() if ln and not ln.startswith("#")]
            assert len(lines) > 10, f"export_csv too short: {len(lines)}"
    print(f"  OK {label}")
'

echo "[7/7] Checking built frontend & optional HTTPS Caddy proxy..."
if [ -f "frontend/dist/index.html" ]; then
  echo "  OK frontend/dist/index.html present."
else
  echo "  WARN: frontend/dist/index.html missing (run 'cd frontend && npm ci && npm run build' before prod compose)."
fi

proxy_state="$(docker inspect -f '{{.State.Status}}' firepulse_proxy 2>/dev/null || true)"
if [ "${proxy_state}" = "running" ]; then
  if command -v curl >/dev/null 2>&1; then
    proxy_base="https://localhost"
    if ! curl -k -fsS -I "${proxy_base}/" >/dev/null 2>&1; then
      if curl -fsS -I "http://localhost/" >/dev/null 2>&1; then
        proxy_base="http://localhost"
      fi
    fi
    for p in "/" "/api/v1/health/"; do
      if ! curl -k -fsS "${proxy_base}${p}" >/dev/null; then
        echo "FAIL: Proxy ${proxy_base}${p} GET failed" >&2
        exit 1
      fi
    done
    echo "  OK Caddy proxy (${proxy_base}) / and /api/v1/health/ return 200"
    for asset in frontend/dist/assets/*.mjs frontend/dist/assets/*.js; do
      [ -e "${asset}" ] || continue
      fname="$(basename "${asset}")"
      headers="$(curl -k -sI "${proxy_base}/assets/${fname}")"
      status_line="$(printf '%s\n' "${headers}" | head -n 1 | tr -d '\r')"
      ct_line="$(printf '%s\n' "${headers}" | grep -i '^content-type:' | tr -d '\r' || true)"
      ct_lower="$(printf '%s' "${ct_line}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${status_line}" != *"200"* ]] || [[ "${ct_lower}" != *"javascript"* ]]; then
        echo "FAIL: /assets/${fname} (${status_line}, ${ct_line})" >&2
        exit 1
      fi
      echo "  OK Proxy asset MIME: /assets/${fname} -> ${ct_line#*: }"
    done
  else
    echo "  WARN: host curl not found; skipped Caddy probe."
  fi
else
  echo "  SKIP: firepulse_proxy not running (dev stack active)."
fi

echo "=== Preflight Demo Check PASSED ==="
