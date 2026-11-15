"""Build 0.25-degree forest-fraction cells for the FirePulse prediction layer.

Inputs:
- ESA WorldCover 2021 v200 tiles (10 m), cropped/resampled to 0.0025 deg with GDAL.
- Gabon ADM0/ADM1 GeoJSON boundaries.

Output:
- data/processed/prediction/forest_cells.csv
- data/processed/prediction/forest_manifest.json

The output keeps every 0.25-degree cell whose centroid falls inside Gabon.
``forest_fraction`` is the share of valid 250 m pixels classified as tree cover
(10) or mangroves (95). Cropland (40), built-up (50) and water (80) fractions are
kept for context and for an optional low-human-pressure proxy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import Point, shape
from shapely.prepared import prep

GRID_DEG = 0.25
PIXEL_DEG = 0.0025
PIXELS_PER_CELL = int(round(GRID_DEG / PIXEL_DEG))
FOREST_CLASSES = {10, 95}
CROPLAND_CLASS = 40
BUILTUP_CLASS = 50
WATER_CLASS = 80


def load_features(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["features"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(
    raster_path: Path,
    adm0_path: Path,
    adm1_path: Path,
    output_dir: Path,
    forest_threshold: float,
) -> dict:
    country = shape(load_features(adm0_path)[0]["geometry"])
    country_prepared = prep(country)
    provinces = []
    for feature in load_features(adm1_path):
        props = feature["properties"]
        provinces.append(
            {
                "code": props.get("shapeISO") or props.get("code"),
                "name": (props.get("shapeName") or props.get("name") or "").strip(),
                "geometry": shape(feature["geometry"]),
            }
        )

    with rasterio.open(raster_path) as src:
        data = src.read(1)
        transform = src.transform
        nodata = src.nodata
        width, height = src.width, src.height

    rows: list[dict] = []
    for row in range(height // PIXELS_PER_CELL):
        lat0 = round(transform.f + (row * PIXELS_PER_CELL) * transform.e, 2)
        for col in range(width // PIXELS_PER_CELL):
            lon0 = round(transform.c + (col * PIXELS_PER_CELL) * transform.a, 2)
            centroid = Point(lon0 + GRID_DEG / 2, lat0 + GRID_DEG / 2)
            if not country_prepared.contains(centroid):
                continue
            window = data[
                row * PIXELS_PER_CELL : (row + 1) * PIXELS_PER_CELL,
                col * PIXELS_PER_CELL : (col + 1) * PIXELS_PER_CELL,
            ]
            valid = window != nodata if nodata is not None else np.ones_like(window, dtype=bool)
            valid_count = int(valid.sum())
            if valid_count == 0:
                continue
            values, counts = np.unique(window[valid], return_counts=True)
            counts_by_class = {int(v): int(c) for v, c in zip(values, counts)}
            forest = sum(counts_by_class.get(c, 0) for c in FOREST_CLASSES)
            cropland = counts_by_class.get(CROPLAND_CLASS, 0)
            builtup = counts_by_class.get(BUILTUP_CLASS, 0)
            water = counts_by_class.get(WATER_CLASS, 0)
            tree = counts_by_class.get(10, 0)
            mangrove = counts_by_class.get(95, 0)

            province_code = None
            province_name = None
            for province in provinces:
                if province["geometry"].contains(centroid):
                    province_code = province["code"]
                    province_name = province["name"]
                    break
            if province_code is None:
                continue

            forest_fraction = forest / valid_count
            rows.append(
                {
                    "cell_id": f"{lat0:.2f}_{lon0:.2f}",
                    "lat0": f"{lat0:.2f}",
                    "lon0": f"{lon0:.2f}",
                    "province_code": province_code,
                    "province_name": province_name,
                    "valid_pixels": valid_count,
                    "forest_fraction": round(forest_fraction, 6),
                    "tree_fraction": round(tree / valid_count, 6),
                    "mangrove_fraction": round(mangrove / valid_count, 6),
                    "cropland_fraction": round(cropland / valid_count, 6),
                    "builtup_fraction": round(builtup / valid_count, 6),
                    "water_fraction": round(water / valid_count, 6),
                    "is_forest": forest_fraction >= forest_threshold,
                }
            )

    rows.sort(key=lambda r: (r["province_code"], r["lat0"], r["lon0"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "forest_cells.csv"
    fields = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    forest_cells = [r for r in rows if r["is_forest"]]
    manifest = {
        "schema_version": 1,
        "artifact_kind": "firepulse-prediction-forest-cells",
        "grid_deg": GRID_DEG,
        "pixel_deg": PIXEL_DEG,
        "forest_classes": sorted(FOREST_CLASSES),
        "forest_threshold": forest_threshold,
        "source": "ESA WorldCover 2021 v200, 10 m, tiles N00E009/N00E012/S03E009/S03E012/S06E009/S06E012",
        "source_url_template": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif",
        "raster_sha256": sha256(raster_path),
        "adm0_sha256": sha256(adm0_path),
        "adm1_sha256": sha256(adm1_path),
        "cells": len(rows),
        "forest_cells": len(forest_cells),
        "forest_area_share": round(len(forest_cells) / len(rows), 4) if rows else 0,
        "csv_sha256": sha256(csv_path),
        "notes": "Static 2021 land-cover mask; not a time-varying forest map. Cells are selected by centroid inside Gabon.",
    }
    (output_dir / "forest_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raster",
        type=Path,
        default=Path(
            r"C:\Users\Danie\AppData\Local\Temp\opencode\worldcover\worldcover_gabon_250m.tif"
        ),
    )
    parser.add_argument("--adm0", type=Path, default=Path("data/boundaries/gabon_adm0.geojson"))
    parser.add_argument("--adm1", type=Path, default=Path("data/boundaries/gabon_adm1.geojson"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/prediction"))
    parser.add_argument("--forest-threshold", type=float, default=0.30)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.raster, args.adm0, args.adm1, args.output, args.forest_threshold), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
