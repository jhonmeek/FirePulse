"""Export consolidated monthly calibration series, SHA-256 checksum, and provenance for M1."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min

from apps.harmonization.models import CalibrationRun, HarmonizedMonthSeries
from apps.observations.models import HotspotObservation, ImportBatch, StaticFlareMaskCell

CALIBRATION_CSV_COLUMNS = [
    "region",
    "region_name",
    "filter_static",
    "month",
    "calibration_split",
    "modis_count",
    "modis_terra_count",
    "modis_aqua_count",
    "viirs_snpp_count",
    "viirs_noaa20_count",
    "harmonized_value",
    "ci_low",
    "ci_high",
    "baseline_median",
    "sensor_regime",
    "coverage_status",
    "method_name",
    "method_version",
    "reference_scale",
]


def _default_output_path() -> Path:
    if Path("/data").exists():
        return Path("/data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv")
    return (
        Path(settings.BASE_DIR).parent
        / "data"
        / "backups"
        / "m1-benchmark-validation"
        / "m2_calibration_monthly_series.csv"
    )


def _detect_git_commit(cli_value: str | None) -> str | None:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    env_val = os.getenv("SOURCE_COMMIT") or os.getenv("GIT_COMMIT")
    if env_val and env_val.strip():
        return env_val.strip()
    repo_root = Path(settings.BASE_DIR).parent
    if (repo_root / ".git").exists():
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except OSError:
            return None
    return None


def _collect_db_provenance(db_source_label: str | None) -> dict:
    batch_dates = ImportBatch.objects.aggregate(min_d=Min("min_date"), max_d=Max("max_date"))
    return {
        "db_source": db_source_label or os.getenv("POSTGRES_HOST", "db"),
        "database_name": settings.DATABASES["default"].get("NAME"),
        "import_batch_count": ImportBatch.objects.count(),
        "hotspot_observation_count": HotspotObservation.objects.count(),
        "static_mask_cell_count": StaticFlareMaskCell.objects.count(),
        "observation_min_date": batch_dates["min_d"].isoformat() if batch_dates["min_d"] else None,
        "observation_max_date": batch_dates["max_d"].isoformat() if batch_dates["max_d"] else None,
    }


def _calibration_split(month_date, run: CalibrationRun) -> str:
    if run.train_start <= month_date <= run.train_end:
        return "train"
    if run.test_start <= month_date <= run.test_end:
        return "test"
    return "other"


def _csv_val(val) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_export(csv_path: Path, sha_path: Path, manifest_path: Path) -> int:
    if not csv_path.is_file():
        raise CommandError(f"Missing calibration export CSV: {csv_path}")
    raw_bytes = csv_path.read_bytes()
    actual_sha = _sha256_bytes(raw_bytes)

    if not sha_path.is_file():
        raise CommandError(f"Missing calibration checksum file: {sha_path}")
    expected_sha = sha_path.read_text(encoding="utf-8").strip().split()[0]
    if actual_sha != expected_sha:
        raise CommandError(f"SHA-256 mismatch against {sha_path.name}")

    if not manifest_path.is_file():
        raise CommandError(f"Missing calibration export manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_kind") != "firepulse-m2-calibration-series":
        raise CommandError("Unrecognized calibration export manifest artifact_kind.")
    if actual_sha != manifest.get("csv_sha256"):
        raise CommandError(f"SHA-256 mismatch against {manifest_path.name}")

    lines = raw_bytes.decode("utf-8").splitlines()
    data_rows = max(0, len(lines) - 1)
    if data_rows != manifest.get("row_count"):
        raise CommandError(
            f"Row count mismatch on {csv_path.name}: csv={data_rows}, manifest={manifest.get('row_count')}"
        )
    return data_rows


class Command(BaseCommand):
    """Export M2 active calibration monthly counts, SHA-256 checksum, and provenance manifest."""

    help = "Export consolidated M2 monthly calibration series (all regions & filter_static modes) with SHA-256."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            default=None,
            help="Target CSV file path (default: /data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv)",
        )
        parser.add_argument(
            "--source-commit",
            default=None,
            help="Git commit SHA used for provenance metadata (falls back to SOURCE_COMMIT env or git HEAD).",
        )
        parser.add_argument(
            "--db-source",
            default=None,
            help="Optional description of the source database snapshot/instance.",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify calibration CSV against its .sha256 file and manifest.json.",
        )

    def handle(self, *args, **options) -> None:
        csv_path = Path(options["output"]) if options["output"] else _default_output_path()
        sha_path = Path(f"{csv_path}.sha256")
        manifest_path = csv_path.parent / "manifest.json"

        if options["verify"]:
            row_count = _verify_export(csv_path, sha_path, manifest_path)
            self.stdout.write(
                self.style.SUCCESS(f"Verified calibration CSV ({row_count} rows) against {sha_path.name} and manifest.json")
            )
            return

        runs = list(
            CalibrationRun.objects.filter(is_active=True, region__isnull=False)
            .select_related("region")
            .order_by("region__region_type", "region__code", "-filter_static")
        )
        if not runs:
            raise CommandError("No active CalibrationRun records found; run build_baseline_series first.")

        buf = StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(CALIBRATION_CSV_COLUMNS)

        run_summaries: list[dict] = []
        total_rows = 0

        for run in runs:
            series_rows = list(
                HarmonizedMonthSeries.objects.filter(calibration_run=run).order_by("month")
            )
            for row in series_rows:
                writer.writerow(
                    [
                        run.region.code,
                        run.region.name,
                        _csv_val(row.filter_static),
                        row.month.strftime("%Y-%m"),
                        _calibration_split(row.month, run),
                        _csv_val(row.modis_count),
                        _csv_val(row.modis_terra_count),
                        _csv_val(row.modis_aqua_count),
                        _csv_val(row.viirs_snpp_count),
                        _csv_val(row.viirs_noaa20_count),
                        _csv_val(row.harmonized_value),
                        _csv_val(row.ci_low),
                        _csv_val(row.ci_high),
                        _csv_val(row.baseline_median),
                        row.sensor_regime,
                        row.coverage_status,
                        run.method_name,
                        run.method_version,
                        run.reference_scale,
                    ]
                )
            total_rows += len(series_rows)
            run_summaries.append(
                {
                    "region": run.region.code,
                    "region_name": run.region.name,
                    "filter_static": run.filter_static,
                    "rows": len(series_rows),
                    "first_month": series_rows[0].month.strftime("%Y-%m") if series_rows else None,
                    "last_month": series_rows[-1].month.strftime("%Y-%m") if series_rows else None,
                    "train_start": run.train_start.isoformat(),
                    "train_end": run.train_end.isoformat(),
                    "test_start": run.test_start.isoformat(),
                    "test_end": run.test_end.isoformat(),
                    "method_name": run.method_name,
                    "method_version": run.method_version,
                    "reference_scale": run.reference_scale,
                    "calibration_created_at_utc": run.created_at.isoformat(),
                    "params": run.params_json,
                    "metrics": run.metrics_json,
                }
            )

        csv_bytes = buf.getvalue().encode("utf-8")
        csv_sha256 = _sha256_bytes(csv_bytes)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_bytes(csv_bytes)
        sha_path.write_bytes(f"{csv_sha256}  {csv_path.name}\n".encode("utf-8"))

        manifest = {
            "artifact_kind": "firepulse-m2-calibration-series",
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": _detect_git_commit(options.get("source_commit")),
            "db_provenance": _collect_db_provenance(options.get("db_source")),
            "spatial_aggregation": "PostGIS ST_Within(observations_hotspotobservation.position, observations_region.geom)",
            "static_mask_definition": (
                "filter_static=true keeps hotspot_type=0 AND NOT is_static_masked (0.05 deg mask); "
                "filter_static=false keeps all detections."
            ),
            "source_tables": [
                "harmonization_calibrationrun (is_active=true)",
                "harmonization_harmonizedmonthseries",
            ],
            "columns": CALIBRATION_CSV_COLUMNS,
            "csv_file": csv_path.name,
            "sha256_file": sha_path.name,
            "csv_sha256": csv_sha256,
            "row_count": total_rows,
            "region_run_count": len(run_summaries),
            "runs": run_summaries,
        }
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        manifest_path.write_bytes(manifest_text.encode("utf-8"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {total_rows} calibration series rows ({len(run_summaries)} region-runs) to {csv_path}"
            )
        )
