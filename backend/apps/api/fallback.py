"""Server-side offline JSON snapshot fallback when PostgreSQL/PostGIS is unavailable."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.http import HttpResponse

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
SERIES_CSV_COLUMNS = [
    "region",
    "month",
    "filter_static",
    "modis_count",
    "viirs_snpp_count",
    "viirs_noaa20_count",
    "harmonized_value",
    "ci_low",
    "ci_high",
    "baseline_median",
    "anomaly_percent",
    "anomaly_absolute",
    "sensor_regime",
    "coverage_status",
    "method_version",
]


def render_series_csv_response(
    export_id: str,
    rows: list[list],
    *,
    fallback: bool = False,
) -> HttpResponse:
    """Serialize harmonized series rows as an HTTP CSV attachment."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(SERIES_CSV_COLUMNS)
    writer.writerows(rows)
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="firepulse_{export_id}_series.csv"'
    if fallback:
        response["X-FirePulse-Cache"] = "FALLBACK"
        response["Cache-Control"] = "no-store"
    return response


def get_snapshot_dir() -> Path:
    configured = getattr(settings, "DEMO_SNAPSHOT_DIR", None)
    if configured:
        return Path(configured)
    if Path("/data").exists():
        return Path("/data/backups/demo_snapshot")
    return Path(settings.BASE_DIR).parent / "data" / "backups" / "demo_snapshot"


def _safe_region_code(raw: str | None, default: str = "GA") -> str | None:
    code = (raw or default).strip()
    if not _SAFE_CODE_RE.fullmatch(code):
        return None
    return code


def _load_snapshot_json(filename: str) -> dict | None:
    snap_dir = get_snapshot_dir()
    if not snap_dir.is_dir():
        return None
    target = (snap_dir / filename).resolve()
    try:
        root = snap_dir.resolve()
    except OSError:
        return None
    if target.parent != root or not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def has_offline_snapshot() -> bool:
    manifest = _load_snapshot_json("snapshot_manifest.json")
    return bool(manifest and manifest.get("artifact_kind") == "firepulse-demo-snapshot")


def _in_month_str_window(month_str: str, start_month: date | None, end_month: date | None) -> bool:
    try:
        year_s, mon_s = month_str.split("-", 1)
        m_date = date(int(year_s), int(mon_s), 1)
    except (ValueError, AttributeError):
        return False
    if start_month and m_date < start_month:
        return False
    if end_month and m_date > end_month:
        return False
    return True


def _suffix(filter_static: bool) -> str:
    return "static" if filter_static else "raw"


def fallback_regions(include_geom: bool) -> dict | None:
    payload = _load_snapshot_json("regions.json")
    if payload is None:
        return None
    if include_geom:
        return payload
    return {
        "regions": [{**item, "geometry": None} for item in payload.get("regions", [])],
    }


def fallback_coverage(region_code: str) -> dict | None:
    code = _safe_region_code(region_code)
    if code is None:
        return None
    payload = _load_snapshot_json("coverage.json")
    if payload is None:
        return None
    return {
        **payload,
        "region": code,
    }


def fallback_calendar(
    region_code: str,
    filter_static: bool,
    start_month: date | None,
    end_month: date | None,
    custom_geom,
) -> dict | None:
    if custom_geom is not None:
        return None
    code = _safe_region_code(region_code)
    if code is None:
        return None
    payload = _load_snapshot_json(f"calendar_{code}_{_suffix(filter_static)}.json")
    if payload is None:
        return None
    if start_month is None and end_month is None:
        return payload

    series = [
        item
        for item in payload.get("series", [])
        if _in_month_str_window(item.get("month", ""), start_month, end_month)
    ]
    return {
        **payload,
        "period": {
            "start": series[0]["month"] if series else None,
            "end": series[-1]["month"] if series else None,
        },
        "series": series,
    }


def fallback_anomalies(
    region_code: str,
    filter_static: bool,
    top_n: int,
    start_month: date | None,
    end_month: date | None,
    custom_geom,
) -> dict | None:
    if custom_geom is not None:
        return None
    code = _safe_region_code(region_code)
    if code is None:
        return None
    sfx = _suffix(filter_static)
    payload = _load_snapshot_json(f"anomalies_{code}_{sfx}.json")
    if payload is None:
        return None

    if start_month is None and end_month is None:
        return {
            **payload,
            "top_positive": list(payload.get("top_positive", []))[:top_n],
            "top_negative": list(payload.get("top_negative", []))[:top_n],
        }

    cal = _load_snapshot_json(f"calendar_{code}_{sfx}.json")
    if cal is None:
        return None

    def _serialize(item: dict) -> dict:
        return {
            "month": item["month"],
            "harmonized_value": item["harmonized_value"],
            "baseline_median": item["baseline_median"],
            "anomaly_percent": item["anomaly_percent"],
            "anomaly_absolute": item["anomaly_absolute"],
            "sensor_regime": item["sensor_regime"],
        }

    valid = [
        item
        for item in cal.get("series", [])
        if item.get("anomaly_percent") is not None
        and _in_month_str_window(item.get("month", ""), start_month, end_month)
    ]
    top_positive = [_serialize(i) for i in sorted(valid, key=lambda x: x["anomaly_percent"], reverse=True)[:top_n]]
    top_negative = [_serialize(i) for i in sorted(valid, key=lambda x: x["anomaly_percent"])[:top_n]]
    return {
        **payload,
        "top_positive": top_positive,
        "top_negative": top_negative,
    }


def fallback_methodology(region_code: str, filter_static: bool) -> dict | None:
    code = _safe_region_code(region_code)
    if code is None:
        return None
    return _load_snapshot_json(f"methodology_{code}_{_suffix(filter_static)}.json")


def _region_geometry(code: str) -> GEOSGeometry | None:
    if code == "GA":
        return None
    regions_payload = _load_snapshot_json("regions.json")
    if regions_payload is None:
        return None
    for item in regions_payload.get("regions", []):
        if item.get("code") == code and item.get("geometry"):
            return GEOSGeometry(json.dumps(item["geometry"]), srid=4326)
    return None


def _filter_static_mask_features(filter_geom: GEOSGeometry | None) -> list[dict]:
    mask_payload = _load_snapshot_json("hotspots_static_mask_GA.json")
    if mask_payload is None:
        return []
    out: list[dict] = []
    for feat in mask_payload.get("features", []):
        if feat.get("properties", {}).get("layer") != "static_flare_mask":
            continue
        if filter_geom is not None:
            geom_obj = feat.get("geometry")
            if not geom_obj or not filter_geom.intersects(GEOSGeometry(json.dumps(geom_obj), srid=4326)):
                continue
        out.append(feat)
        if len(out) >= 1000:
            break
    return out


def fallback_hotspots(
    mode: str,
    agg: str,
    region_code: str | None,
    filter_static: bool,
    include_static_cells: bool,
    limit: int,
    month_date: date | None,
    start_month: date | None,
    end_month: date | None,
    custom_geom,
) -> dict | None:
    if mode != "grid":
        return None
    code = _safe_region_code(region_code, default="GA")
    if code is None:
        return None
    sfx = _suffix(filter_static)

    if agg == "cell" and custom_geom is None and month_date is None and start_month is None and end_month is None:
        payload = _load_snapshot_json(f"hotspots_grid_cell_{code}_{sfx}.json")
        if payload is None:
            return None
        features = [
            feat
            for feat in payload.get("features", [])
            if feat.get("properties", {}).get("layer") != "static_flare_mask"
        ][:limit]
        if include_static_cells:
            features.extend(_filter_static_mask_features(_region_geometry(code)))
        return {"type": "FeatureCollection", "mode": mode, "agg": agg, "features": features}

    monthly_payload = _load_snapshot_json(f"hotspots_grid_monthly_{sfx}.json")
    if monthly_payload is None:
        return None

    filter_geom = custom_geom if custom_geom is not None else _region_geometry(code)
    if code != "GA" and custom_geom is None and filter_geom is None:
        return None

    cells = monthly_payload.get("cells", {})
    if filter_geom is None:
        allowed_cells = set(cells.keys())
    else:
        allowed_cells = {
            cid
            for cid, poly in cells.items()
            if filter_geom.intersects(GEOSGeometry(json.dumps(poly), srid=4326))
        }

    exact_month_str = month_date.strftime("%Y-%m") if month_date else None
    rows = monthly_payload.get("rows", [])

    features = []
    if agg == "cell":
        grouped: dict[str, dict] = {}
        for cell_id, m_str, mod, snpp, n20, fm, fs, fn in rows:
            if cell_id not in allowed_cells:
                continue
            if exact_month_str is not None:
                if m_str != exact_month_str:
                    continue
            elif not _in_month_str_window(m_str, start_month, end_month):
                continue
            acc = grouped.setdefault(
                cell_id,
                {
                    "months_count": 0,
                    "modis_count": 0,
                    "viirs_snpp_count": 0,
                    "viirs_noaa20_count": 0,
                    "frp_sum_modis": 0.0,
                    "frp_sum_snpp": 0.0,
                    "frp_sum_noaa20": 0.0,
                },
            )
            acc["months_count"] += 1
            acc["modis_count"] += mod
            acc["viirs_snpp_count"] += snpp
            acc["viirs_noaa20_count"] += n20
            acc["frp_sum_modis"] += fm
            acc["frp_sum_snpp"] += fs
            acc["frp_sum_noaa20"] += fn

        ordered = sorted(
            grouped.items(),
            key=lambda kv: (-kv[1]["viirs_snpp_count"], -kv[1]["modis_count"], kv[0]),
        )[:limit]
        for cell_id, acc in ordered:
            features.append(
                {
                    "type": "Feature",
                    "geometry": cells[cell_id],
                    "properties": {
                        "layer": "grid_cell_summary",
                        "cell_id": cell_id,
                        "months_count": acc["months_count"],
                        "modis_count": acc["modis_count"],
                        "viirs_snpp_count": acc["viirs_snpp_count"],
                        "viirs_noaa20_count": acc["viirs_noaa20_count"],
                        "frp_sum_modis": round(acc["frp_sum_modis"], 2),
                        "frp_sum_snpp": round(acc["frp_sum_snpp"], 2),
                        "frp_sum_noaa20": round(acc["frp_sum_noaa20"], 2),
                    },
                }
            )
    else:
        for cell_id, m_str, mod, snpp, n20, _fm, _fs, _fn in rows:
            if cell_id not in allowed_cells:
                continue
            if exact_month_str is not None:
                if m_str != exact_month_str:
                    continue
            elif not _in_month_str_window(m_str, start_month, end_month):
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": cells[cell_id],
                    "properties": {
                        "layer": "grid_cell_month",
                        "cell_id": cell_id,
                        "month": m_str,
                        "modis_count": mod,
                        "viirs_snpp_count": snpp,
                        "viirs_noaa20_count": n20,
                    },
                }
            )
            if len(features) >= limit:
                break

    if include_static_cells:
        features.extend(_filter_static_mask_features(filter_geom))

    return {
        "type": "FeatureCollection",
        "mode": mode,
        "agg": agg,
        "features": features,
    }


def fallback_export_series_csv(
    region_code: str,
    filter_static: bool,
    start_month: date | None,
    end_month: date | None,
    custom_geom,
) -> HttpResponse | None:
    cal = fallback_calendar(region_code, filter_static, start_month, end_month, custom_geom)
    if cal is None:
        return None
    code = _safe_region_code(region_code)
    meth = _load_snapshot_json(f"methodology_{code}_{_suffix(filter_static)}.json") or {}
    method_version = (
        (meth.get("active_run") or {}).get("method_version")
        or (cal.get("method") or {}).get("version")
        or "v2.0"
    )
    export_id = cal.get("region", {}).get("id", code)
    rows = [
        [
            export_id,
            item["month"],
            filter_static,
            item["modis_count"],
            item["viirs_snpp_count"],
            item["viirs_noaa20_count"],
            item["harmonized_value"],
            item["ci_low"],
            item["ci_high"],
            item["baseline_median"],
            item["anomaly_percent"],
            item["anomaly_absolute"],
            item["sensor_regime"],
            item["coverage_status"],
            method_version,
        ]
        for item in cal.get("series", [])
    ]
    return render_series_csv_response(export_id, rows, fallback=True)
