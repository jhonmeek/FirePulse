"""Build a partial offshore GeoJSON from a FIRMS acquisition and an EEZ reference."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source: Path, manifest_path: Path, boundary: Path, output: Path) -> int:
    # Shapely is an optional dependency for this geographic export.
    try:
        from shapely.geometry import Point, shape
    except ImportError as exc:
        raise ImportError("Install geographic dependencies: pip install -r pipeline/requirements-geo.txt") from exc

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("csv_sha256") != sha(source) or manifest.get("product") != "VIIRS_NOAA20_NRT":
        raise ValueError("Input does not match the NOAA-20 NRT acquisition manifest")
    raw = json.loads(boundary.read_text(encoding="utf-8-sig"))
    features = raw.get("features", [])
    if len(features) != 1 or str(features[0].get("properties", {}).get("mrgid")) != "8476":
        raise ValueError("Expected Marine Regions Gabon EEZ MRGID 8476")
    geom = shape(features[0]["geometry"])
    if geom.is_empty or not geom.is_valid:
        raise ValueError("Invalid EEZ geometry")
    start = date.fromisoformat(manifest["requested_start"])
    end = date.fromisoformat(manifest["requested_end"])
    west, south, east, north = manifest["requested_bbox"]
    minx, miny, maxx, maxy = geom.bounds
    if not (west <= minx and south <= miny and east >= maxx and north >= maxy):
        raise ValueError("Acquisition bbox does not cover the full reference EEZ bounds")
    result = []
    row_count = 0
    type_values_present = False
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"longitude", "latitude", "acq_date", "acq_time", "satellite", "instrument"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("FIRMS CSV is missing required columns")
        for row in reader:
            row_count += 1
            lon, lat = float(row["longitude"]), float(row["latitude"])
            acquired = date.fromisoformat(row["acq_date"])
            if not (math.isfinite(lon) and math.isfinite(lat) and west <= lon <= east and south <= lat <= north and start <= acquired <= end):
                raise ValueError("Invalid coordinates or date")
            raw_time = (row.get("acq_time") or "").strip()
            time = raw_time.zfill(4)
            if not raw_time or len(time) != 4 or not time.isascii() or not time.isdigit() or int(time[:2]) > 23 or int(time[2:]) > 59:
                raise ValueError("Invalid acquisition time")
            if row.get("satellite") not in ("N20", "NOAA-20", "NOAA20") or (row.get("instrument") or "").upper() != "VIIRS":
                raise ValueError("Satellite or instrument does not match requested NOAA-20 VIIRS")
            raw_frp = (row.get("frp") or "").strip()
            try:
                frp = float(raw_frp) if raw_frp else None
            except ValueError as exc:
                raise ValueError("Invalid FRP") from exc
            if frp is not None and (not math.isfinite(frp) or frp < 0):
                raise ValueError("Invalid FRP")
            nasa_type = (row.get("type") or "").strip() or None
            if not geom.contains(Point(lon, lat)):
                continue
            type_values_present = type_values_present or nasa_type is not None
            result.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                           "properties": {"acq_date": row["acq_date"], "acq_time_utc": time,
                                          "satellite": row["satellite"], "instrument": row["instrument"],
                                          "frp": frp, "nasa_type": nasa_type}})
    if row_count != manifest.get("rows"):
        raise ValueError("Row count does not match acquisition manifest")
    doc = {"type": "FeatureCollection", "features": result, "metadata": {
        "dataset": "NASA FIRMS VIIRS NOAA-20 NRT", "product_verification": "requested_not_independently_verified",
        "period_start": start.isoformat(), "period_end": end.isoformat(), "retrieved_at_utc": manifest["retrieved_at_utc"],
        "source_csv_sha256": sha(source), "boundary_sha256": sha(boundary), "boundary_mrgid": 8476,
        "boundary_source": "Marine Regions World EEZ v12, 2023", "boundary_predicate": "strictly within",
        "count": len(result), "source_rows": row_count, "outside_or_boundary_rows": row_count-len(result),
        "observation_coverage": "unknown", "nasa_type_column_present": manifest.get("type_column_present", False),
        "nasa_type_available": type_values_present,
        "limitations": ["Partial five-day NRT snapshot, not real-time monitoring.", "Heat detections, not confirmed fires or flares.",
                        "EEZ is a scientific reference, not an authoritative legal determination."]}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return len(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "boundary", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(f"Prepared {build(args.source, args.manifest, args.boundary, args.output)} offshore thermal detections")


if __name__ == "__main__":
    main()
