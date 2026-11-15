"""Download, clean and verify MCD12Q1 LC_Type1 rasters for a region (default: Gabon).

Example (inside the backend container):
    python manage.py fetch_mcd12q1 --years 2001-2025
"""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.gis.gdal import GDALRaster, SpatialReference
from django.core.management.base import BaseCommand, CommandError

from apps.observations.land_cover import MCD12Q1Lookup
from apps.observations.mcd12q1_acquire import (
    BAND, CELL_SIZE_M, FILL, ORNL_API, PRODUCT, SINUSOIDAL_PROJ4, Window,
    build_mosaics, inverse_sinusoidal, parse_subset, plan_centers, subset_url,
    window_for_bbox, year_chunks, GRID_X0, GRID_Y0,
)

USER_AGENT = "FirePulse-research-client/1.0"


def _bounds(geojson_path: Path) -> tuple[float, float, float, float]:
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    xs, ys = [], []

    def walk(coords):
        if isinstance(coords[0], (int, float)):
            xs.append(coords[0]); ys.append(coords[1])
        else:
            for item in coords:
                walk(item)

    for feature in data["features"]:
        walk(feature["geometry"]["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def _parse_years(text: str) -> list[int]:
    if "-" in text:
        start, end = (int(v) for v in text.split("-", 1))
        return list(range(start, end + 1))
    return [int(v) for v in text.split(",")]


def _get_json(url: str, attempts: int = 4) -> dict:
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            client_error = isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code != 429
            if attempt == attempts or client_error:
                raise CommandError(f"request failed after {attempts} attempts: {url} ({exc})") from exc
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Download MCD12Q1 LC_Type1 from the NASA ORNL DAAC web service, clean, mosaic and verify it."

    def add_arguments(self, parser):
        parser.add_argument("--boundary", default="/data/boundaries/gabon_adm0.geojson")
        parser.add_argument("--buffer-deg", type=float, default=0.15)
        parser.add_argument("--years", default="2001-2025")
        parser.add_argument("--out-dir", default="/data/raw/mcd12q1/gabon")
        parser.add_argument("--cache-dir", default="/data/raw/mcd12q1/ornl-cache")
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--verify-points", type=int, default=30)
        parser.add_argument("--seed", type=int, default=20261115)

    def handle(self, *args, **opts):
        years = _parse_years(opts["years"])
        west, south, east, north = _bounds(Path(opts["boundary"]))
        buf = opts["buffer_deg"]
        bbox = (west - buf, south - buf, east + buf, north + buf)
        window = window_for_bbox(*bbox)
        out_dir, cache_dir = Path(opts["out_dir"]), Path(opts["cache_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        existing = [p.name for p in out_dir.glob("*.tif")]
        if existing:
            raise CommandError(f"{out_dir} already contains rasters ({len(existing)}); choose an empty directory")

        centers = plan_centers(window)
        jobs = [(lat, lon, chunk) for lat, lon in centers for chunk in year_chunks(years)]
        self.stdout.write(f"Window {window.ncols}x{window.nrows} px, {len(centers)} subsets x "
                          f"{len(year_chunks(years))} year chunks = {len(jobs)} requests")

        def fetch(job):
            lat, lon, chunk = job
            cache = cache_dir / f"{lat}_{lon}_{min(chunk)}-{max(chunk)}.json.gz"
            url = subset_url(lat, lon, chunk)
            if not cache.exists():
                payload = _get_json(url)
                tmp = cache.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as stream:
                    json.dump(payload, stream)
                tmp.replace(cache)
            with gzip.open(cache, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            blocks = parse_subset(payload)
            got = sorted(b.year for b in blocks)
            if got != sorted(chunk):
                raise CommandError(f"{url}: expected years {chunk}, got {got}")
            return url, cache.name, blocks

        done, results = 0, []
        with ThreadPoolExecutor(max_workers=opts["workers"]) as pool:
            for result in pool.map(fetch, jobs):
                results.append(result)
                done += 1
                if done % 8 == 0 or done == len(jobs):
                    self.stdout.write(f"  {done}/{len(jobs)} subsets validated")

        blocks = [b for _, _, bs in results for b in bs]
        mosaics = build_mosaics(window, years, blocks)
        self.stdout.write("Mosaics complete: full coverage, overlaps consistent, values in LC_Type1 domain")

        srs = SpatialReference(SINUSOIDAL_PROJ4)
        files = {}
        for year, mosaic in sorted(mosaics.items()):
            path = out_dir / f"mcd12q1_lc_type1_gabon_{year}.tif"
            raster = GDALRaster({
                "driver": "GTiff", "name": str(path), "srid": 4326,
                "width": window.ncols, "height": window.nrows, "datatype": 1,
                "origin": [window.geotransform[0], window.geotransform[3]],
                "scale": [CELL_SIZE_M, -CELL_SIZE_M],
                "bands": [{"data": bytes(mosaic.data), "nodata_value": FILL}],
                "papsz_options": {"compress": "deflate", "tiled": "yes"},
            })
            raster.srs = srs
            del raster
            files[year] = {"file": path.name, "sha256": _sha256(path),
                           "histogram": {str(k): v for k, v in mosaic.histogram().items()},
                           "subsets": mosaic.blocks}
        self.stdout.write(f"Wrote {len(files)} GeoTIFF to {out_dir}")

        verification = self._verify(window, mosaics, out_dir, years, opts["verify_points"], opts["seed"])
        manifest = {
            "artifact_kind": "firepulse-mcd12q1-land-cover", "schema_version": 1,
            "product": f"{PRODUCT}.061", "band": BAND, "classification": "IGBP (LC_Type1)",
            "source": "NASA ORNL DAAC MODIS/VIIRS Land Product Subsets web service",
            "source_api": ORNL_API, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "boundary": Path(opts["boundary"]).name, "bbox_wgs84_buffered": bbox,
            "grid": {"crs": SINUSOIDAL_PROJ4, "cell_size_m": CELL_SIZE_M, "origin": [GRID_X0, GRID_Y0],
                     "window": {"col0": window.col0, "row0": window.row0, "ncols": window.ncols, "nrows": window.nrows},
                     "geotransform": window.geotransform},
            "nodata": FILL,
            "cleaning": ["cell size and corners aligned on native MODIS grid (no resampling)",
                         "band LC_Type1 only; values restricted to IGBP 1-17 and fill 255",
                         "overlapping subsets identical pixel by pixel",
                         "window fully covered for every year", "no gap filling or reclassification"],
            "requests": [{"url": url, "cache": cache} for url, cache, _ in results],
            "years": {str(y): v for y, v in files.items()},
            "verification": verification,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if verification["mismatches"]:
            raise CommandError(f"verification failed: {verification['mismatches']} mismatches")
        self.stdout.write(self.style.SUCCESS(
            f"Verified {verification['checked']} independent single-pixel queries: 0 mismatch"))

    def _verify(self, window: Window, mosaics, out_dir: Path, years, count: int, seed: int) -> dict:
        """Compare random pixels with independent 1-pixel ORNL queries, read back through the lookup."""
        rng = random.Random(seed)
        lookup = MCD12Q1Lookup.from_directory(out_dir, radius=0)
        check_years = sorted({years[0], years[len(years) // 2], years[-1]})
        checks, mismatches = [], 0
        for _ in range(count):
            col = window.col0 + rng.randrange(window.ncols)
            row = window.row0 + rng.randrange(window.nrows)
            lat, lon = inverse_sinusoidal(GRID_X0 + (col + 0.5) * CELL_SIZE_M, GRID_Y0 - (row + 0.5) * CELL_SIZE_M)
            lat, lon = round(lat, 6), round(lon, 6)
            for year in check_years:
                url = (f"{ORNL_API}/{PRODUCT}/subset?latitude={lat}&longitude={lon}&band={BAND}"
                       f"&startDate=A{year}001&endDate=A{year}001&kmAboveBelow=0&kmLeftRight=0")
                items = _get_json(url)["subset"]
                if len(items) != 1 or int(items[0]["modis_date"][1:5]) != year:
                    raise CommandError(f"unexpected verification response for {url}")
                expected = items[0]["data"][0]
                mosaic_value = mosaics[year].value_at(lat, lon)
                sample = lookup(lat, lon, year)
                read_back = FILL if sample is None or sample.igbp_class is None else sample.igbp_class
                ok = expected == mosaic_value == read_back
                mismatches += not ok
                checks.append({"lat": lat, "lon": lon, "year": year, "ornl": expected,
                               "mosaic": mosaic_value, "geotiff": read_back, "ok": ok})
        return {"method": "random pixels vs independent kmAboveBelow=0 ORNL queries, read back from GeoTIFF",
                "seed": seed, "years": check_years, "checked": len(checks), "mismatches": mismatches, "checks": checks}
