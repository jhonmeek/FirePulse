"""Export a deterministic offline JSON snapshot of FirePulse API v1 endpoints for demo fallback."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.contrib.gis.db.models.functions import AsGeoJSON
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.test import override_settings
from rest_framework.test import APIClient

from apps.api.fallback import regions_payload_matches_manifest, validate_snapshot_manifest
from apps.observations.models import GridCellMonth, Region


def _default_snapshot_dir() -> Path:
    configured = getattr(settings, "DEMO_SNAPSHOT_DIR", None)
    if configured:
        return Path(configured)
    if Path("/data").exists():
        return Path("/data/backups/demo_snapshot")
    return Path(settings.BASE_DIR).parent / "data" / "backups" / "demo_snapshot"


def _write_json(path: Path, payload: dict, *, compact: bool = False) -> dict:
    if compact:
        encoded = (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    else:
        encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return {
        "file": path.name,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _build_grid_monthly_payload(filter_static: bool) -> dict:
    qs = GridCellMonth.objects.filter(filter_static=filter_static)
    cells = {
        row["cell_id"]: json.loads(row["geojson_text"])
        for row in qs.values("cell_id").annotate(geojson_text=Max(AsGeoJSON("geom"))).order_by("cell_id")
    }
    rows = [
        [
            row["cell_id"],
            row["month"].strftime("%Y-%m"),
            row["modis_count"],
            row["viirs_snpp_count"],
            row["viirs_noaa20_count"],
            round(row["frp_sum_modis"] or 0.0, 2),
            round(row["frp_sum_snpp"] or 0.0, 2),
            round(row["frp_sum_noaa20"] or 0.0, 2),
        ]
        for row in qs.values(
            "cell_id",
            "month",
            "modis_count",
            "viirs_snpp_count",
            "viirs_noaa20_count",
            "frp_sum_modis",
            "frp_sum_snpp",
            "frp_sum_noaa20",
        ).order_by("cell_id", "month")
    ]
    return {"cells": cells, "rows": rows}


def _verify_snapshot_manifest(out_dir: Path, manifest: dict) -> None:
    try:
        validate_snapshot_manifest(manifest)
    except ValueError as exc:
        raise CommandError(f"Snapshot verification failed: {exc}") from exc
    manifest_regions = tuple(manifest["regions"])
    for entry in manifest["files"]:
        target = out_dir / entry["file"]
        if not target.is_file():
            raise CommandError(f"Snapshot verification failed: missing {entry['file']}")
        raw_bytes = target.read_bytes()
        expected_bytes = entry.get("bytes")
        if isinstance(expected_bytes, int) and len(raw_bytes) != expected_bytes:
            raise CommandError(f"Snapshot verification failed: byte size mismatch on {entry['file']}")
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if actual_sha != entry["sha256"]:
            raise CommandError(f"Snapshot verification failed: SHA-256 mismatch on {entry['file']}")
        if entry["file"] == "regions.json" and not regions_payload_matches_manifest(
            raw_bytes, manifest_regions
        ):
            raise CommandError("Snapshot verification failed: regions.json does not match manifest regions")


class Command(BaseCommand):
    """Export all precomputed API v1 JSON payloads + SHA-256 manifest for offline fallback."""

    help = "Export deterministic offline JSON snapshot of API v1 endpoints and SHA-256 manifest."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            default=None,
            help="Target snapshot directory (default: /data/backups/demo_snapshot)",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify SHA-256 checksums of an existing snapshot_manifest.json without re-exporting.",
        )

    def handle(self, *args, **options) -> None:
        out_dir = Path(options["output"]) if options["output"] else _default_snapshot_dir()
        if options["verify"]:
            manifest_path = out_dir / "snapshot_manifest.json"
            if not manifest_path.is_file():
                raise CommandError(f"Missing snapshot manifest: {manifest_path}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            _verify_snapshot_manifest(out_dir, manifest)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Verified {len(manifest.get('files', []))} snapshot files in {out_dir}"
                )
            )
            return

        out_dir.mkdir(parents=True, exist_ok=True)

        client = APIClient(HTTP_HOST="localhost")
        region_codes = list(Region.objects.order_by("region_type", "code").values_list("code", flat=True))
        if not region_codes:
            region_codes = ["GA"]

        targets: list[tuple[str, str]] = [
            ("health.json", "/api/v1/health/"),
            ("regions.json", "/api/v1/regions/?include_geom=true"),
            ("coverage.json", "/api/v1/coverage/?region=GA"),
            (
                "hotspots_static_mask_GA.json",
                "/api/v1/hotspots/?mode=grid&agg=cell&region=GA&filter_static=true&include_static_cells=true&limit=2000",
            ),
        ]
        for code in region_codes:
            targets.extend(
                [
                    (f"calendar_{code}_static.json", f"/api/v1/calendar/?region={code}&filter_static=true"),
                    (f"calendar_{code}_raw.json", f"/api/v1/calendar/?region={code}&filter_static=false"),
                    (f"anomalies_{code}_static.json", f"/api/v1/anomalies/?region={code}&filter_static=true&top_n=50"),
                    (f"anomalies_{code}_raw.json", f"/api/v1/anomalies/?region={code}&filter_static=false&top_n=50"),
                    (f"methodology_{code}_static.json", f"/api/v1/methodology/?region={code}&filter_static=true"),
                    (f"methodology_{code}_raw.json", f"/api/v1/methodology/?region={code}&filter_static=false"),
                    (
                        f"hotspots_grid_cell_{code}_static.json",
                        f"/api/v1/hotspots/?mode=grid&agg=cell&region={code}&filter_static=true&limit=2000",
                    ),
                    (
                        f"hotspots_grid_cell_{code}_raw.json",
                        f"/api/v1/hotspots/?mode=grid&agg=cell&region={code}&filter_static=false&limit=2000",
                    ),
                ]
            )

        manifest_files: list[dict] = []
        health_payload: dict | None = None
        with override_settings(FORCE_SNAPSHOT_FALLBACK=False):
            for filename, url in targets:
                res = client.get(url)
                if res.status_code != 200:
                    raise CommandError(f"Snapshot export failed on {url} (HTTP {res.status_code}).")
                payload = res.json()
                if filename == "health.json":
                    health_payload = payload
                manifest_files.append(_write_json(out_dir / filename, payload))

        for filename, filter_static in (
            ("hotspots_grid_monthly_static.json", True),
            ("hotspots_grid_monthly_raw.json", False),
        ):
            manifest_files.append(
                _write_json(
                    out_dir / filename,
                    _build_grid_monthly_payload(filter_static),
                    compact=True,
                )
            )

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
        _verify_snapshot_manifest(out_dir, manifest)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(manifest_files)} API snapshot files to {out_dir}"
            )
        )
