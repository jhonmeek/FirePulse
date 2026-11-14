"""Export a deterministic offline JSON snapshot of FirePulse API v1 endpoints for demo fallback."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rest_framework.test import APIClient

from apps.observations.models import Region


def _default_snapshot_dir() -> Path:
    if Path("/data").exists():
        return Path("/data/backups/demo_snapshot")
    return Path(settings.BASE_DIR).parent / "data" / "backups" / "demo_snapshot"


def _write_json(path: Path, payload: dict) -> dict:
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return {
        "file": path.name,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


class Command(BaseCommand):
    """Export all precomputed API v1 JSON payloads + SHA-256 manifest for offline fallback."""

    help = "Export deterministic offline JSON snapshot of API v1 endpoints and SHA-256 manifest."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            default=None,
            help="Target snapshot directory (default: /data/backups/demo_snapshot)",
        )

    def handle(self, *args, **options) -> None:
        out_dir = Path(options["output"]) if options["output"] else _default_snapshot_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        client = APIClient(HTTP_HOST="localhost")
        region_codes = list(Region.objects.order_by("region_type", "code").values_list("code", flat=True))
        if not region_codes:
            region_codes = ["GA"]

        targets: list[tuple[str, str]] = [
            ("health.json", "/api/v1/health/"),
            ("regions.json", "/api/v1/regions/?include_geom=true"),
            ("coverage.json", "/api/v1/coverage/?region=GA"),
            ("hotspots_grid_cell_GA_static.json", "/api/v1/hotspots/?mode=grid&agg=cell&region=GA&filter_static=true&limit=2000"),
            ("methodology_GA_static.json", "/api/v1/methodology/?region=GA&filter_static=true"),
            ("methodology_GA_raw.json", "/api/v1/methodology/?region=GA&filter_static=false"),
            ("anomalies_GA_static.json", "/api/v1/anomalies/?region=GA&filter_static=true&top_n=20"),
            ("anomalies_GA_raw.json", "/api/v1/anomalies/?region=GA&filter_static=false&top_n=20"),
        ]
        for code in region_codes:
            targets.append((f"calendar_{code}_static.json", f"/api/v1/calendar/?region={code}&filter_static=true"))
            targets.append((f"calendar_{code}_raw.json", f"/api/v1/calendar/?region={code}&filter_static=false"))

        manifest_files: list[dict] = []
        health_payload: dict | None = None
        for filename, url in targets:
            res = client.get(url)
            if res.status_code != 200:
                raise CommandError(f"Snapshot export failed on {url} (HTTP {res.status_code}).")
            payload = res.json()
            if filename == "health.json":
                health_payload = payload
            manifest_files.append(_write_json(out_dir / filename, payload))

        manifest = {
            "artifact_kind": "firepulse-demo-snapshot",
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "regions": region_codes,
            "health_counts": (health_payload or {}).get("counts", {}),
            "files": manifest_files,
        }
        (out_dir / "snapshot_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(manifest_files)} API snapshot files to {out_dir}"
            )
        )
