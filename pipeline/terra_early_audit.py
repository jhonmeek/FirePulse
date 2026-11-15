"""Reconcile early MODIS Terra country-file detections against M1 monthly counts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

MONTHS = tuple(f"{year:04d}-{month:02d}" for year in (2000, 2001, 2002)
               for month in range(1, 13) if (year, month) >= (2000, 11))
RAW_FIELDS = {"acq_date", "satellite", "instrument", "type"}
MONTHLY_FIELDS = {"region", "dataset_scope", "month", "source", "satellite",
                  "count_raw", "count_type0_candidate"}


def _read_csv(path: Path, required: set[str]):
    try:
        content = path.read_bytes()
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or not required.issubset(fields):
            raise ValueError(f"invalid or duplicate CSV columns: {path}")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed CSV row: {path}:{reader.line_num}")
            rows.append(row)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"cannot read CSV {path}: {exc}") from exc
    return rows, hashlib.sha256(content).hexdigest()


def audit(raw_dir: Path, monthly_path: Path) -> dict:
    counts, type0 = Counter(), Counter()
    hashes, seen = {}, set()
    duplicate_rows = 0
    for year in (2000, 2001, 2002):
        path = raw_dir / f"modis_{year}_Gabon.csv"
        rows, digest = _read_csv(path, RAW_FIELDS)
        hashes[str(path)] = digest
        for row in rows:
            identity = tuple(sorted(row.items()))
            if identity in seen:
                duplicate_rows += 1
            seen.add(identity)
            try:
                acquired = date.fromisoformat(row["acq_date"].strip())
            except ValueError as exc:
                raise ValueError(f"invalid acquisition date in {path}: {row['acq_date']}") from exc
            month = acquired.isoformat()[:7]
            if acquired.year != year or month not in MONTHS:
                raise ValueError(f"date outside expected file/year or audit period: {path}: {acquired}")
            satellite = row["satellite"].strip().lower()
            hotspot_type = row["type"].strip()
            if satellite not in ("terra", "aqua") or row["instrument"].strip().lower() != "modis":
                raise ValueError(f"unexpected satellite or instrument in {path}")
            if hotspot_type not in ("0", "1", "2", "3"):
                raise ValueError(f"invalid hotspot type in {path}: {row['type']!r}")
            if satellite == "terra":
                counts[month] += 1
                type0[month] += hotspot_type == "0"

    monthly_rows, digest = _read_csv(monthly_path, MONTHLY_FIELDS)
    hashes[str(monthly_path)] = digest
    selected = {}
    for row in monthly_rows:
        if row["source"] != "modis" or row["satellite"] != "Terra" or row["region"] != "GA":
            continue
        month = row["month"]
        if month not in MONTHS:
            continue
        if row["dataset_scope"] != "country_file_unverified_geometry":
            raise ValueError(f"unexpected dataset scope for {month}")
        if month in selected:
            raise ValueError(f"duplicate monthly Terra key: {month}")
        values = []
        for field in ("count_raw", "count_type0_candidate"):
            value = row[field]
            if not value or not value.isascii() or not value.isdecimal():
                raise ValueError(f"invalid {field} for {month}: {value!r}")
            values.append(int(value))
        if values[1] > values[0]:
            raise ValueError(f"type 0 count exceeds raw count: {month}")
        selected[month] = values
    missing = sorted(set(MONTHS) - selected.keys())
    if missing:
        raise ValueError(f"missing monthly Terra keys: {', '.join(missing)}")

    records = []
    for month in MONTHS:
        actual = (counts[month], type0[month])
        expected = selected[month]
        records.append({"month": month, "raw_terra": actual[0], "raw_type0": actual[1],
                        "detection_status": "detections_recorded" if actual[0] else "no_detections_recorded",
                        "observation_coverage": "unknown",
                        "monthly_terra": expected[0], "monthly_type0": expected[1],
                        "difference_terra": actual[0] - expected[0],
                        "difference_type0": actual[1] - expected[1],
                        "match": list(actual) == expected})
    return {"artifact_kind": "firepulse-terra-early-audit", "schema_version": 1,
            "period": {"start": MONTHS[0], "end": MONTHS[-1]},
            "input_sha256": hashes, "months": records, "duplicate_exact_rows": duplicate_rows,
            "totals": {"raw_terra": sum(counts.values()), "raw_type0": sum(type0.values()),
                       "months": len(records), "mismatched_months": sum(not r["match"] for r in records)},
            "status": "match" if all(r["match"] for r in records) else "mismatch",
            "limitations": ["Observation coverage is unknown; no detections do not establish coverage or absence of fire.",
                            "This checks country-file counts, not boundary geometry or scientific validity of harmonization.",
                            "2000 is partial; the audit does not assert completeness or provenance of the source exports."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--monthly", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new JSON file; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        result = audit(args.raw_dir, args.monthly)
        payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except (ValueError, OSError) as exc:
        print(f"audit error: {exc}", file=sys.stderr)
        return 2
    return 0 if result["status"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
