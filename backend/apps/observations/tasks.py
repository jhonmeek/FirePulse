import os
import json
import csv
import hashlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celery import shared_task
from django.contrib.gis.geos import Point
from django.core.management import call_command
from redis import Redis

from apps.observations.models import Region


def prepare_gabon_import(raw_csv: Path, output_dir: Path) -> tuple[Path, int]:
    """Keep the unmodified NASA file and create an import CSV inside GA only."""
    region = Region.objects.get(code="GA")
    output_dir.mkdir(parents=True, exist_ok=False)
    target = output_dir / raw_csv.name.replace("viirs_noaa20", "viirs-noaa20", 1)
    retained = 0
    with raw_csv.open("r", encoding="utf-8-sig", newline="") as source, target.open("x", encoding="utf-8", newline="") as destination:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("FIRMS CSV has no header")
        writer = csv.DictWriter(destination, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            point = Point(float(row["longitude"]), float(row["latitude"]), srid=4326)
            if region.geom.contains(point):
                writer.writerow(row)
                retained += 1
    manifest = {
        "source_csv": raw_csv.name,
        "source_sha256": hashlib.sha256(raw_csv.read_bytes()).hexdigest(),
        "import_csv": target.name,
        "import_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "retained_within_ga": retained,
        "spatial_rule": "strictly_within_region_GA",
        "observation_coverage": "unknown",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target, retained


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def acquire_firms_nrt(self):
    """Fetch a sliding UTC window from FIRMS and ingest GA observations idempotently."""
    if os.environ.get("FIRMS_NRT_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return {"status": "disabled"}
    key = os.environ.get("FIRMS_MAP_KEY", "")
    if not key:
        raise RuntimeError("FIRMS_MAP_KEY is required when FIRMS_NRT_ENABLED is true")
    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    lock = Redis.from_url(broker_url).lock("firms-nrt-acquisition-lock", timeout=3300, blocking=False)
    if not lock.acquire():
        return {"status": "already_running"}

    try:
        root = Path(os.environ.get("FIRMS_NRT_DIR", "/data/nrt"))
        root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        lookback_days = int(os.environ.get("FIRMS_NRT_LOOKBACK_DAYS", "2"))
        if not 1 <= lookback_days <= 5:
            raise ValueError("FIRMS_NRT_LOOKBACK_DAYS must be between 1 and 5")
        day = now.date() - timedelta(days=lookback_days - 1)
        output = root / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}"
        output.mkdir(parents=True, exist_ok=False)
        repo_pipeline = Path("/pipeline")
        script = repo_pipeline / "firms_area_acquire.py"
        if not script.exists():
            raise RuntimeError("FIRMS acquisition pipeline is not mounted in the worker")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_pipeline) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run(
            [sys.executable, str(script), "--product", "VIIRS_NOAA20_NRT", "--start", day.isoformat(), "--days", str(lookback_days), "--output-dir", str(output)],
            check=True, capture_output=True, text=True, timeout=90, env=env,
        )
        raw_files = list(output.glob("*.csv"))
        source_manifests = list(output.glob("*.manifest.json"))
        if len(raw_files) != 1 or len(source_manifests) != 1:
            raise ValueError("Expected one FIRMS CSV and its acquisition manifest")
        source_manifest = json.loads(source_manifests[0].read_text(encoding="utf-8"))
        if (
            source_manifest.get("csv_file") != raw_files[0].name
            or source_manifest.get("csv_sha256") != hashlib.sha256(raw_files[0].read_bytes()).hexdigest()
            or source_manifest.get("product") != "VIIRS_NOAA20_NRT"
        ):
            raise ValueError("FIRMS acquisition manifest does not match the downloaded CSV")
        import_dir = output / "import"
        _, retained = prepare_gabon_import(raw_files[0], import_dir)
        if retained:
            call_command("import_firms", data_dir=str(import_dir), skip_rebuild_if_unchanged=True)
        return {"status": "completed", "window_start": day.isoformat(), "window_end": now.date().isoformat(), "retrieved_at_utc": now.isoformat(), "gabon_rows": retained}
    finally:
        lock.release()
