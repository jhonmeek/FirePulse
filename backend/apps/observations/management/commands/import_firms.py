"""Idempotent NASA FIRMS CSV loader, static-flare masker, and 0.25 deg grid builder."""

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.api.cache import invalidate_api_cache
from apps.observations.models import (
    ConfidenceTierChoices,
    HotspotObservation,
    ImportBatch,
    ProcessingLevelChoices,
    SourceChoices,
)

SOURCE_PREFIX_MAP = {
    "modis": SourceChoices.MODIS,
    "viirs-snpp": SourceChoices.VIIRS_SNPP,
    "viirs-jpss1": SourceChoices.VIIRS_NOAA20,
    "viirs-noaa20": SourceChoices.VIIRS_NOAA20,
    "viirs-jpss2": SourceChoices.VIIRS_NOAA21,
    "viirs-noaa21": SourceChoices.VIIRS_NOAA21,
}


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_source(filename: str) -> str:
    lower = filename.lower()
    for prefix, source in SOURCE_PREFIX_MAP.items():
        if lower.startswith(prefix):
            return source
    raise CommandError(f"Cannot infer sensor source from filename: {filename}")


def _normalize_confidence(source: str, raw: str) -> str:
    val = (raw or "").strip().lower()
    if source == SourceChoices.MODIS:
        try:
            score = float(val)
        except ValueError:
            return ConfidenceTierChoices.NOMINAL
        if score < 30:
            return ConfidenceTierChoices.LOW
        if score < 80:
            return ConfidenceTierChoices.NOMINAL
        return ConfidenceTierChoices.HIGH
    if val.startswith("l"):
        return ConfidenceTierChoices.LOW
    if val.startswith("h"):
        return ConfidenceTierChoices.HIGH
    return ConfidenceTierChoices.NOMINAL


def _parse_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    return float(raw)


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    hhmm = acq_time.strip().zfill(4)
    return datetime.strptime(f"{acq_date.strip()} {hhmm}", "%Y-%m-%d %H%M").replace(
        tzinfo=timezone.utc
    )


def _row_to_observation(row: dict[str, str], batch: ImportBatch, source: str) -> HotspotObservation:
    lat = float(row["latitude"])
    lon = float(row["longitude"])
    acq_dt = _parse_acq_datetime(row["acq_date"], row["acq_time"])
    satellite = (row.get("satellite") or "").strip()
    instrument = (row.get("instrument") or ("MODIS" if source == SourceChoices.MODIS else "VIIRS")).strip()
    version = (row.get("version") or "").strip()
    is_nrt = "nrt" in version.lower() or batch.processing_level == ProcessingLevelChoices.NRT

    if source == SourceChoices.MODIS:
        mir = _parse_float(row.get("brightness"))
        tir = _parse_float(row.get("bright_t31"))
    else:
        mir = _parse_float(row.get("bright_ti4"))
        tir = _parse_float(row.get("bright_ti5"))

    conf_raw = (row.get("confidence") or "").strip()
    sig = f"{source}|{satellite}|{row['acq_date']}|{row['acq_time']}|{lat:.5f}|{lon:.5f}|{version}"
    obs_hash = hashlib.sha256(sig.encode("utf-8")).hexdigest()

    return HotspotObservation(
        batch=batch,
        source=source,
        satellite=satellite,
        instrument=instrument,
        acquired_at=acq_dt,
        position=Point(lon, lat, srid=4326),
        frp=_parse_float(row.get("frp")),
        brightness_mir=mir,
        brightness_tir=tir,
        scan=_parse_float(row.get("scan")),
        track=_parse_float(row.get("track")),
        confidence_raw=conf_raw,
        confidence_tier=_normalize_confidence(source, conf_raw),
        daynight=(row.get("daynight") or "D").strip()[:1].upper(),
        hotspot_type=int(row["type"]) if row.get("type") not in (None, "") else 0,
        is_static_masked=False,
        product_version=version,
        is_nrt=is_nrt,
        original_hash=obs_hash,
    )


def rebuild_static_mask_and_flag() -> int:
    """Identify 0.05 deg persistent flare/static cells in PostGIS and flag observations."""
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE observations_staticflaremaskcell RESTART IDENTITY;")
        cursor.execute(
            """
            WITH binned AS (
                SELECT
                    FLOOR(ST_Y(position) * 20.0) / 20.0 AS lat0,
                    FLOOR(ST_X(position) * 20.0) / 20.0 AS lon0,
                    COUNT(*) FILTER (WHERE hotspot_type IN (2, 3)) AS type23_count,
                    COUNT(DISTINCT DATE_TRUNC('month', acquired_at))
                        FILTER (WHERE source = 'viirs-snpp') AS active_months_snpp
                FROM observations_hotspotobservation
                GROUP BY 1, 2
            ),
            flagged AS (
                SELECT
                    lat0,
                    lon0,
                    type23_count,
                    active_months_snpp,
                    CASE
                        WHEN type23_count >= 20 AND active_months_snpp >= 48
                            THEN 'persistent_type23_and_snpp_frequency'
                        WHEN type23_count >= 20 THEN 'type23_static_threshold'
                        ELSE 'snpp_high_persistence_48m'
                    END AS reason
                FROM binned
                WHERE type23_count >= 20 OR active_months_snpp >= 48
            )
            INSERT INTO observations_staticflaremaskcell
                (cell_id, grid_deg, geom, type23_count, active_months_snpp, reason, created_at)
            SELECT
                TO_CHAR(ROUND(lat0::numeric, 2), 'FM990.00') || '_' || TO_CHAR(ROUND(lon0::numeric, 2), 'FM990.00'),
                0.05,
                ST_SetSRID(ST_MakeEnvelope(lon0, lat0, lon0 + 0.05, lat0 + 0.05), 4326),
                type23_count,
                active_months_snpp,
                reason,
                NOW()
            FROM flagged;
            """
        )
        masked_cells = cursor.rowcount
        cursor.execute("UPDATE observations_hotspotobservation SET is_static_masked = FALSE WHERE is_static_masked = TRUE;")
        cursor.execute(
            """
            UPDATE observations_hotspotobservation AS o
            SET is_static_masked = TRUE
            FROM observations_staticflaremaskcell AS m
            WHERE ST_Intersects(o.position, m.geom);
            """
        )
    return masked_cells


def rebuild_grid_cell_months() -> int:
    """Rebuild 0.25 deg monthly aggregates for filter_static=True and filter_static=False."""
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE observations_gridcellmonth RESTART IDENTITY;")
        for filter_static in (True, False):
            where_clause = "WHERE hotspot_type = 0 AND NOT is_static_masked" if filter_static else ""
            cursor.execute(
                f"""
                WITH binned AS (
                    SELECT
                        FLOOR(ST_Y(position) * 4.0) / 4.0 AS lat0,
                        FLOOR(ST_X(position) * 4.0) / 4.0 AS lon0,
                        DATE_TRUNC('month', acquired_at)::date AS month,
                        COUNT(*) FILTER (WHERE source = 'modis') AS modis_count,
                        COUNT(*) FILTER (WHERE source = 'modis' AND satellite = 'Terra') AS modis_terra_count,
                        COUNT(*) FILTER (WHERE source = 'modis' AND satellite = 'Aqua') AS modis_aqua_count,
                        COUNT(*) FILTER (WHERE source = 'viirs-snpp') AS viirs_snpp_count,
                        COUNT(*) FILTER (WHERE source = 'viirs-noaa20') AS viirs_noaa20_count,
                        COALESCE(SUM(frp) FILTER (WHERE source = 'modis'), 0.0) AS frp_sum_modis,
                        COALESCE(SUM(frp) FILTER (WHERE source = 'viirs-snpp'), 0.0) AS frp_sum_snpp,
                        COALESCE(SUM(frp) FILTER (WHERE source = 'viirs-noaa20'), 0.0) AS frp_sum_noaa20
                    FROM observations_hotspotobservation
                    {where_clause}
                    GROUP BY 1, 2, 3
                )
                INSERT INTO observations_gridcellmonth (
                    cell_id, geom, centroid, month, filter_static,
                    modis_count, modis_terra_count, modis_aqua_count,
                    viirs_snpp_count, viirs_noaa20_count,
                    frp_sum_modis, frp_sum_snpp, frp_sum_noaa20
                )
                SELECT
                    TO_CHAR(ROUND(lat0::numeric, 2), 'FM990.00') || '_' || TO_CHAR(ROUND(lon0::numeric, 2), 'FM990.00'),
                    ST_SetSRID(ST_MakeEnvelope(lon0, lat0, lon0 + 0.25, lat0 + 0.25), 4326),
                    ST_SetSRID(ST_MakePoint(lon0 + 0.125, lat0 + 0.125), 4326),
                    month,
                    %s,
                    modis_count, modis_terra_count, modis_aqua_count,
                    viirs_snpp_count, viirs_noaa20_count,
                    frp_sum_modis, frp_sum_snpp, frp_sum_noaa20
                FROM binned;
                """,
                [filter_static],
            )
        cursor.execute("SELECT COUNT(*) FROM observations_gridcellmonth;")
        return cursor.fetchone()[0]


class Command(BaseCommand):
    """Idempotently load NASA FIRMS CSVs into PostGIS and build masks/grid aggregates."""

    help = "Import NASA FIRMS CSV files, build 0.05 deg static flare mask, and aggregate 0.25 deg grid."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--data-dir",
            default="/data/raw/gabon",
            help="Directory containing NASA FIRMS CSV files",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-import files even if their SHA-256 is already recorded",
        )
        parser.add_argument(
            "--rebuild-only",
            action="store_true",
            help="Skip CSV ingestion and only rebuild static flare mask and 0.25 deg grid",
        )

    def handle(self, *args, **options) -> None:
        if not options["rebuild_only"]:
            data_dir = Path(options["data_dir"])
            if not data_dir.exists():
                raise CommandError(f"Data directory not found: {data_dir}")

            csv_files = sorted(data_dir.glob("*.csv"))
            if not csv_files:
                raise CommandError(f"No CSV files found in {data_dir}")

            imported_files = 0
            total_rows = 0
            for csv_path in csv_files:
                sha = _file_sha256(csv_path)
                existing = ImportBatch.objects.filter(file_sha256=sha).first()
                if existing and not options["force"]:
                    continue
                if existing and options["force"]:
                    existing.delete()

                source = _infer_source(csv_path.name)
                proc_level = (
                    ProcessingLevelChoices.NRT
                    if "nrt" in csv_path.name.lower()
                    else ProcessingLevelChoices.SP
                )

                with transaction.atomic():
                    batch = ImportBatch.objects.create(
                        source=source,
                        processing_level=proc_level,
                        file_name=csv_path.name,
                        file_sha256=sha,
                    )
                    objs: list[HotspotObservation] = []
                    versions: set[str] = set()
                    dates: list[datetime] = []
                    nrt_rows = 0

                    with csv_path.open("r", encoding="utf-8", newline="") as fh:
                        for row in csv.DictReader(fh):
                            obs = _row_to_observation(row, batch, source)
                            objs.append(obs)
                            versions.add(obs.product_version)
                            dates.append(obs.acquired_at)
                            if obs.is_nrt:
                                nrt_rows += 1
                            if len(objs) >= 5000:
                                HotspotObservation.objects.bulk_create(objs, ignore_conflicts=True)
                                objs.clear()

                    if objs:
                        HotspotObservation.objects.bulk_create(objs, ignore_conflicts=True)

                    batch.row_count = len(dates)
                    batch.product_version = ",".join(sorted(v for v in versions if v))[:30]
                    if nrt_rows > 0:
                        batch.processing_level = ProcessingLevelChoices.NRT
                        if nrt_rows < len(dates):
                            batch.notes = f"mixed_sp_nrt_rows={nrt_rows}/{len(dates)}"
                    if dates:
                        batch.min_date = min(dates).date()
                        batch.max_date = max(dates).date()
                    batch.save()

                    imported_files += 1
                    total_rows += len(dates)

            self.stdout.write(
                f"CSV ingestion finished: {imported_files} new/updated files ({total_rows} rows)."
            )

        masked_cells = rebuild_static_mask_and_flag()
        grid_rows = rebuild_grid_cell_months()
        invalidate_api_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Static flare mask: {masked_cells} cells; GridCellMonth rows: {grid_rows}."
            )
        )
