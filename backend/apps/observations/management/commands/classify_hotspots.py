"""Classify FIRMS archive hotspots with MCD12Q1 land cover and produce a validation report.

Example (inside the backend container):
    python manage.py classify_hotspots
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, Point
from django.core.management.base import BaseCommand, CommandError

from apps.observations.fire_typing import DEFAULT_MIXED_THRESHOLD, classify_observation
from apps.observations.land_cover import MCD12Q1Lookup

FILE_RE = re.compile(r"^(modis|viirs-snpp|viirs-jpss1)_(\d{4})_.+\.csv$")
VEGETATION_LANDSCAPES = ("tropical_forest", "forest", "savanna", "grassland", "shrubland",
                         "cropland", "cropland_mosaic", "wetland", "urban")
# Well-known sites with unambiguous land cover, used as sanity checks (not ground truth).
REFERENCE_SITES = [
    {"name": "Océan Atlantique au large d'Iguéla", "lat": -1.5, "lon": 8.8, "expected": [17]},
    {"name": "Océan Atlantique au large de Gamba", "lat": -3.0, "lon": 9.6, "expected": [17]},
    {"name": "Libreville centre", "lat": 0.39, "lon": 9.45, "expected": [13]},
    {"name": "Parc national de l'Ivindo", "lat": 0.2, "lon": 12.6, "expected": [2]},
    {"name": "Parc national de Minkébé", "lat": 1.5, "lon": 12.8, "expected": [2]},
    {"name": "Plateaux Batéké", "lat": -2.1, "lon": 14.05, "expected": [8, 9, 10]},
]
DRY_SEASON_MONTHS = {6, 7, 8, 9}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _share(counter: Counter) -> dict:
    total = sum(counter.values())
    return {k: round(v / total, 4) for k, v in counter.most_common()} if total else {}


class Command(BaseCommand):
    help = "Classify FIRMS hotspots by thermal type and MCD12Q1 landscape, with a validation report."

    def add_arguments(self, parser):
        parser.add_argument("--firms-dir", default="/data/raw/gabon")
        parser.add_argument("--land-cover-dir", default="/data/raw/mcd12q1/gabon")
        parser.add_argument("--boundary", default="/data/boundaries/gabon_adm0.geojson")
        parser.add_argument("--output", default="/data/processed/hotspot-types/gabon-hotspot-types.json")
        parser.add_argument("--detections-output", default="/data/processed/hotspot-types/gabon-hotspot-types-detections.csv.gz")
        parser.add_argument("--area-samples", type=int, default=20000)
        parser.add_argument("--stability-samples", type=int, default=3000)
        parser.add_argument("--seed", type=int, default=20261115)

    def handle(self, *args, **opts):
        output, det_output = Path(opts["output"]), Path(opts["detections_output"])
        for path in (output, det_output):
            if path.exists():
                raise CommandError(f"{path} already exists; choose another path")
        output.parent.mkdir(parents=True, exist_ok=True)
        lookup = MCD12Q1Lookup.from_directory(opts["land_cover_dir"])
        area_lookup = MCD12Q1Lookup.from_directory(opts["land_cover_dir"], radius=0)
        boundary_doc = json.loads(Path(opts["boundary"]).read_text(encoding="utf-8"))
        gabon = GEOSGeometry(json.dumps(boundary_doc["features"][0]["geometry"]), srid=4326)
        inside = gabon.prepared

        files = sorted(p for p in Path(opts["firms_dir"]).glob("*.csv") if FILE_RE.match(p.name))
        if not files:
            raise CommandError("no FIRMS CSV found")

        totals = defaultdict(lambda: {"thermal": Counter(), "status": Counter(), "landscape": Counter(), "flags": Counter()})
        veg_by_source = defaultdict(Counter)        # type 0, status inferred
        veg_by_year = defaultdict(lambda: defaultdict(Counter))
        veg_by_month = defaultdict(Counter)          # landscape -> month
        veg_by_igbp = Counter()
        veg_points = []                              # (lat, lon, landscape) for the stability check
        thermal_vs_igbp = defaultdict(Counter)       # thermal type -> land cover category
        outside_boundary = Counter()
        n = 0
        with gzip.open(det_output, "wt", encoding="utf-8", newline="") as det_stream:
            writer = csv.writer(det_stream)
            writer.writerow(["source", "acq_date", "acq_time", "latitude", "longitude", "firms_type", "thermal_type",
                             "landscape", "status", "igbp_class", "land_cover_year", "dominant_fraction", "flags", "label"])
            for path in files:
                source = FILE_RE.match(path.name).group(1)
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    for row in csv.DictReader(stream):
                        kind = (row.get("type") or "").strip()
                        observation = {"latitude": float(row["latitude"]), "longitude": float(row["longitude"]),
                                       "acquired_at": row["acq_date"], "type_nasa": int(kind) if kind else None}
                        result = classify_observation(observation, lookup)
                        cls, lc = result["classification"], result["land_cover"] or {}
                        bucket = totals[source]
                        bucket["thermal"][result["thermal_type"]] += 1
                        bucket["status"][cls["status"]] += 1
                        bucket["landscape"][cls["landscape"]] += 1
                        bucket["flags"].update(cls["flags"])
                        thermal_vs_igbp[result["thermal_type"]][lc.get("category", "unknown")] += 1
                        if not inside.contains(Point(observation["longitude"], observation["latitude"], srid=4326)):
                            outside_boundary[result["thermal_type"]] += 1
                        if result["thermal_type"] == "presumed_vegetation_fire" and cls["status"] == "inferred":
                            veg_by_source[source][cls["landscape"]] += 1
                            veg_by_year[source][row["acq_date"][:4]][cls["landscape"]] += 1
                            veg_by_month[cls["landscape"]][int(row["acq_date"][5:7])] += 1
                            veg_by_igbp[str(lc["igbp_class"])] += 1
                            veg_points.append((observation["latitude"], observation["longitude"], cls["landscape"]))
                        frac = lc.get("dominant_fraction")
                        writer.writerow([source, row["acq_date"], row["acq_time"], row["latitude"], row["longitude"], kind,
                                         result["thermal_type"], cls["landscape"], cls["status"], lc.get("igbp_class"),
                                         lc.get("year"), "" if frac is None else round(frac, 4), "|".join(cls["flags"]), cls["label"]])
                        n += 1
                self.stdout.write(f"  {path.name}: classified (running total {n})")

        area = self._area_shares(area_lookup, gabon, opts["area_samples"], opts["seed"])
        stability = self._stability(area_lookup, veg_points, opts["stability_samples"], opts["seed"])
        enrichment = {}
        for source, counts in veg_by_source.items():
            fire_share = _share(counts)
            enrichment[source] = {k: round(fire_share[k] / area["mean_share"][k], 2)
                                  for k in fire_share if area["mean_share"].get(k)}
        dry = {k: round(sum(m[i] for i in DRY_SEASON_MONTHS) / sum(m.values()), 3)
               for k, m in veg_by_month.items() if sum(m.values()) >= 100}
        sites = []
        for site in REFERENCE_SITES:
            values = {}
            for year in area_lookup.years:
                sample = area_lookup(site["lat"], site["lon"], year)
                values[year] = None if sample is None else sample.igbp_class
            agree = sum(v in site["expected"] for v in values.values())
            sites.append({**site, "agreement_years": agree, "years": len(values),
                          "observed": dict(Counter(values.values()).most_common())})

        report = {
            "artifact_kind": "firepulse-hotspot-types", "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": {"function": "apps.observations.fire_typing.classify_hotspot",
                       "land_cover": "NASA MCD12Q1 C6.1 LC_Type1 (IGBP), same year or nearest available",
                       "window": "3x3 pixels (~1.5 km)", "mixed_threshold": DEFAULT_MIXED_THRESHOLD,
                       "cause": "never inferred (always unknown)"},
            "inputs": {"firms_files": {p.name: _sha256(p) for p in files},
                       "land_cover_manifest_sha256": _sha256(Path(opts["land_cover_dir"]) / "manifest.json"),
                       "land_cover_years": lookup.years},
            "detections": n,
            "by_source": {s: {k: dict(v.most_common()) for k, v in b.items()} for s, b in sorted(totals.items())},
            "thermal_type_vs_land_cover": {k: dict(v.most_common()) for k, v in thermal_vs_igbp.items()},
            "outside_gabon_boundary": dict(outside_boundary),
            "vegetation_fires_inferred": {
                "by_source_share": {s: _share(c) for s, c in sorted(veg_by_source.items())},
                "by_source_count": {s: dict(c.most_common()) for s, c in sorted(veg_by_source.items())},
                "by_year": {s: {y: dict(c.most_common()) for y, c in sorted(ys.items())} for s, ys in sorted(veg_by_year.items())},
                "by_month": {k: {str(m): c for m, c in sorted(v.items())} for k, v in veg_by_month.items()},
                "dry_season_share_jun_sep": dry,
                "by_igbp_class": dict(veg_by_igbp.most_common()),
            },
            "land_cover_temporal_stability": stability,
            "land_area_share_gabon": area,
            "enrichment_fire_share_over_area_share": enrichment,
            "reference_sites": sites,
            "limitations": [
                "Landscape at the detection location, not the cause of the fire.",
                "MODIS 1 km / VIIRS 375 m footprints vs 500 m land cover: border pixels are uncertain (see mixed).",
                "MCD12Q1 is itself a classification with its own errors; it is not ground truth.",
                "Detections are raw FIRMS rows (no deduplication, no sensor harmonization).",
            ],
        }
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Classified {n} detections -> {output}"))

    def _stability(self, lookup, points, count: int, seed: int) -> dict:
        """For sampled inferred vegetation fires: share of land-cover years with the same landscape."""
        from apps.observations.fire_typing import IGBP_CLASSES
        rng = random.Random(seed)
        sample = rng.sample(points, min(count, len(points)))
        per_landscape = defaultdict(list)
        for lat, lon, landscape in sample:
            same = 0
            for year in lookup.years:
                found = lookup(lat, lon, year)
                code = None if found is None else found.igbp_class
                same += code in IGBP_CLASSES and IGBP_CLASSES[code][1] == landscape
            per_landscape[landscape].append(same / len(lookup.years))
        summary = {}
        for landscape, values in sorted(per_landscape.items(), key=lambda kv: -len(kv[1])):
            values.sort()
            summary[landscape] = {"samples": len(values), "median_same_landscape_share": round(values[len(values) // 2], 3),
                                  "share_stable_80pct": round(sum(v >= 0.8 for v in values) / len(values), 3)}
        return {"samples": len(sample), "seed": seed, "years": len(lookup.years),
                "definition": "share of MCD12Q1 years in which the detection pixel has the same landscape",
                "by_landscape": summary}

    def _area_shares(self, lookup, gabon, count: int, seed: int) -> dict:
        """Landscape shares of Gabon's land area from uniform random points (radius 0)."""
        rng = random.Random(seed)
        west, south, east, north = gabon.extent
        prepared, points = gabon.prepared, []
        while len(points) < count:
            lat, lon = rng.uniform(south, north), rng.uniform(west, east)
            if prepared.contains(Point(lon, lat, srid=4326)):
                points.append((lat, lon))
        from apps.observations.fire_typing import IGBP_CLASSES
        by_year = {}
        for year in lookup.years:
            counter = Counter()
            for lat, lon in points:
                sample = lookup(lat, lon, year)
                code = None if sample is None else sample.igbp_class
                counter[IGBP_CLASSES[code][1] if code in IGBP_CLASSES else "unknown"] += 1
            by_year[str(year)] = _share(counter)
        keys = {k for shares in by_year.values() for k in shares}
        mean = {k: round(sum(s.get(k, 0) for s in by_year.values()) / len(by_year), 4) for k in keys}
        return {"samples": count, "seed": seed, "by_year": by_year,
                "mean_share": dict(sorted(mean.items(), key=lambda kv: -kv[1]))}
