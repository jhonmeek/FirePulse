"""Deterministic inventory and quality audit for NASA FIRMS CSV exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

PRODUCT_RE = re.compile(r"^(modis|viirs-snpp|viirs-jpss1)_(\d{4})_Gabon\.csv$", re.I)
BASE_REQUIRED = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "version", "daynight", "type"}
PRODUCT_FIELDS = {"modis": {"brightness", "bright_t31", "scan", "track", "frp"},
                  "viirs-snpp": {"bright_ti4", "bright_ti5", "scan", "track", "frp"},
                  "viirs-jpss1": {"bright_ti4", "bright_ti5", "scan", "track", "frp"}}
NUMERIC = {"latitude", "longitude", "brightness", "bright_t31", "bright_ti4", "bright_ti5", "scan", "track", "frp"}
DAYNIGHT = {"d", "n"}
TYPE = {"0", "1", "2", "3"}


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _product(name: str) -> tuple[str, int] | tuple[None, None]:
    match = PRODUCT_RE.fullmatch(name)
    return (match.group(1).lower(), int(match.group(2))) if match else (None, None)


def audit(input_dir: Path, output_dir: Path) -> tuple[dict, dict]:
    source = input_dir.resolve()
    target = output_dir.resolve()
    if not source.is_dir():
        raise ValueError("input directory does not exist")
    if target == source or source in target.parents:
        raise ValueError("output must not be inside the raw input directory")
    paths = sorted((p for p in source.rglob("*.csv") if p.is_file()), key=lambda p: p.relative_to(source).as_posix())
    if not paths:
        raise ValueError("input directory contains no CSV files")
    manifests, file_reports, all_rows = [], [], []
    product_counts: dict[str, Counter] = {}
    global_schema: dict[str, set[str]] = {}

    for path in paths:
        rel = path.relative_to(source).as_posix()
        product, filename_year = _product(path.name)
        digest = hashlib.sha256()
        with path.open("rb") as raw:
            for chunk in iter(lambda: raw.read(1024 * 1024), b""):
                digest.update(chunk)
        counts = Counter()
        dates, satellites, versions, types, months = set(), set(), set(), set(), set()
        columns: list[str] = []
        missing_required: Counter = Counter()
        invalid_numeric: Counter = Counter()
        invalid_dates = invalid_times = out_of_bounds = nonfinite = year_mismatch = 0
        malformed = 0
        exact_keys = set()
        duplicates = 0
        read_error = None
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, restkey="__extra__", restval=None)
                columns = reader.fieldnames or []
                global_schema.setdefault(product or "unknown", set()).update(columns)
                required = BASE_REQUIRED | PRODUCT_FIELDS.get(product, set())
                schema_missing = sorted(required - set(columns))
                for row in reader:
                    counts["rows"] += 1
                    if row.get("__extra__") is not None or any(value is None for key, value in row.items() if key != "__extra__"):
                        malformed += 1
                    raw_signature = tuple((key, row.get(key)) for key in columns) + (("__extra__", tuple(row.get("__extra__") or ())),)
                    clean = {k: (v or "").strip() for k, v in row.items() if k != "__extra__"}
                    for key in required & set(columns):
                        if not clean.get(key):
                            missing_required[key] += 1
                    date_text = clean.get("acq_date", "")
                    try:
                        date = datetime.strptime(date_text, "%Y-%m-%d").date()
                        dates.add(date.isoformat()); months.add(date.strftime("%Y-%m"))
                        if filename_year is not None and date.year != filename_year:
                            year_mismatch += 1
                    except ValueError:
                        invalid_dates += bool(date_text)
                    time_text = clean.get("acq_time", "")
                    if time_text:
                        if not time_text.isdigit() or len(time_text) > 4 or int(time_text) > 2359 or int(time_text) % 100 > 59:
                            invalid_times += 1
                        elif len(time_text) < 4:
                            counts["unpadded_times"] += 1
                    for key in ("latitude", "longitude"):
                        try:
                            number = float(clean.get(key, ""))
                            if not math.isfinite(number):
                                nonfinite += 1
                            elif (key == "latitude" and not -90 <= number <= 90) or (key == "longitude" and not -180 <= number <= 180):
                                out_of_bounds += 1
                        except (ValueError, TypeError):
                            if clean.get(key): invalid_numeric[key] += 1
                    for key in NUMERIC - {"latitude", "longitude"}:
                        value = clean.get(key, "")
                        if value:
                            try:
                                if not math.isfinite(float(value)): nonfinite += 1
                            except ValueError:
                                invalid_numeric[key] += 1
                    confidence = clean.get("confidence", "").lower()
                    if confidence:
                        if product == "modis":
                            try:
                                number = float(confidence)
                                if not math.isfinite(number) or not 0 <= number <= 100: counts["invalid_confidence"] += 1
                            except ValueError:
                                counts["invalid_confidence"] += 1
                        elif product in {"viirs-snpp", "viirs-jpss1"} and confidence not in {"l", "n", "h"}:
                            counts["invalid_confidence"] += 1
                    if clean.get("daynight", "").lower() not in DAYNIGHT and clean.get("daynight", ""): counts["invalid_daynight"] += 1
                    kind = clean.get("type", "")
                    if kind and kind not in TYPE: counts["invalid_type"] += 1
                    if clean.get("satellite"): satellites.add(clean["satellite"])
                    if clean.get("version"): versions.add(clean["version"])
                    if kind:
                        types.add(kind)
                        counts[f"type_{kind}"] += 1
                    if raw_signature in exact_keys: duplicates += 1
                    exact_keys.add(raw_signature)
                    all_rows.append((raw_signature, rel))
        except (UnicodeDecodeError, csv.Error, OSError) as exc:
            malformed += 1
            read_error = f"{type(exc).__name__}: {exc}"
            schema_missing = sorted((BASE_REQUIRED | PRODUCT_FIELDS.get(product, set())) - set(columns))
            counts["read_errors"] += 1
        pc = product_counts.setdefault(product or "unknown", Counter())
        pc.update({"files": 1, "rows": counts["rows"], "type_2": counts["type_2"], "type_3": counts["type_3"],
                   "type_2_3": counts["type_2"] + counts["type_3"]})
        manifests.append({"file": rel, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest(), "schema": columns,
                          "rows": counts["rows"], "min_date": min(dates) if dates else None, "max_date": max(dates) if dates else None,
                          "satellites": sorted(satellites), "versions": sorted(versions), "types": sorted(types), "months_observed": sorted(months),
                          "product": product, "filename_year": filename_year})
        file_reports.append({"file": rel, "product": product, "rows": counts["rows"], "schema_missing_columns": schema_missing,
                             "required_empty": dict(sorted(missing_required.items())), "malformed_rows": malformed,
                             "invalid_dates": invalid_dates, "invalid_times": invalid_times, "unpadded_times": counts["unpadded_times"],
                             "coordinates_out_of_bounds": out_of_bounds, "nonfinite_numeric": nonfinite,
                             "invalid_numeric": dict(sorted(invalid_numeric.items())), "invalid_confidence": counts["invalid_confidence"],
                             "invalid_daynight": counts["invalid_daynight"], "invalid_type": counts["invalid_type"],
                             "filename_date_year_mismatch": year_mismatch, "duplicate_exact_rows": duplicates, "read_error": read_error})

    signature_files: dict[tuple, set[str]] = {}
    signature_counts: Counter = Counter()
    for sig, rel in all_rows:
        signature_files.setdefault(sig, set()).add(rel)
        signature_counts[sig] += 1
    cross = Counter()
    for sig, rel in all_rows:
        if len(signature_files[sig]) > 1:
            cross[rel] += 1
    for report in file_reports:
        report["duplicate_exact_rows_inter_file_inclusive"] = cross[report["file"]]
    quality = {"files": len(paths), "rows": sum(m["rows"] for m in manifests), "products": {k: dict(sorted(v.items())) for k, v in sorted(product_counts.items())},
               "files_detail": file_reports, "schema_by_product": {k: sorted(v) for k, v in sorted(global_schema.items())},
               "duplicate_exact_signatures_across_files": sum(1 for files in signature_files.values() if len(files) > 1),
               "duplicate_exact_rows_inter_file": sum(count for sig, count in signature_counts.items() if len(signature_files[sig]) > 1),
               "read_errors": sum(1 for item in file_reports if item["read_error"] is not None),
               "missing_months": {k: {"status": "unknown", "months_observed": sorted({month for item in manifests if item["product"] == k for month in item["months_observed"]})} for k in sorted(product_counts)},
               "notes": ["Missing months have status unknown; this audit cannot establish coverage or imply zero detections.", "No polygon was supplied; coordinates are checked against WGS84 numeric bounds only. No boundary or country-membership claim is made.", "NASA FIRMS AttributesReadme.txt describes WGS84 and collection versions. NASA reported a VIIRS Vxx14IMGML Collection 2 type 0/2 processing issue fixed by reprocessing version 3 (2025-06-15); affected rows cannot be identified from this audit and no values are reclassified."]}
    _json(target / "data_manifest.json", {"files": manifests, "file_count": len(manifests), "row_count": sum(m["rows"] for m in manifests)})
    _json(target / "quality_report.json", quality)
    _write_markdown(target / "m1-data-audit.md", manifests, quality)
    return {"files": manifests, "file_count": len(manifests), "row_count": sum(m["rows"] for m in manifests)}, quality


def _write_markdown(path: Path, manifest: list[dict], quality: dict) -> None:
    lines = ["# M1 n°1 — Inventaire et qualité", "", f"Fichiers CSV : **{len(manifest)}** · lignes : **{quality['rows']}**", "", "## Résumé par produit", "", "| Produit | Fichiers | Lignes |", "|---|---:|---:|"]
    for product, stats in quality["products"].items():
        lines.append(f"| {product} | {stats['files']} | {stats['rows']} |")
    lines += ["", "## Points d’interprétation", "", "- Les mois absents sont `unknown` : ils ne prouvent ni couverture réelle ni zéro détection.", "- Sans polygone, les bornes WGS84 ne prouvent pas l’appartenance au Gabon ni le respect de ses frontières.", "- Les schémas s’appuient sur les colonnes des fichiers et `AttributesReadme.txt` fourni avec les données. Une anomalie de domaine est signalée, jamais corrigée.", "- L’avis NASA FIRMS du 15 juin 2025 décrit un défaut de traitement VIIRS Vxx14IMGML Collection 2 (types 0/2, versions de traitement 1/2, corrigé par version 3). Cet audit ne peut pas déterminer les lignes affectées et ne reclassifie rien : https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html", "- Aucun benchmark n’est revendiqué comme validé.", "", "Détails déterministes : `data_manifest.json` et `quality_report.json`. Aucun horodatage volatile ni chemin absolu n’est enregistré.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    audit(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
