"""Inspect a supplied FIRMS NRT CSV without downloading, changing or classifying it."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path


def inspect_csv(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    counts = Counter(); versions = Counter(); years = Counter(); invalid = Counter(); first = last = None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, restkey="__extra__")
        required = {"latitude", "longitude", "acq_date", "acq_time", "version"}
        if not reader.fieldnames or required - set(reader.fieldnames):
            raise ValueError("missing required FIRMS columns: " + ", ".join(sorted(required - set(reader.fieldnames or []))))
        has_type = "type" in reader.fieldnames
        for line, row in enumerate(reader, 2):
            counts["rows"] += 1
            if row.get("__extra__") or any(value is None for key, value in row.items() if key != "__extra__"):
                invalid["malformed_row"] += 1; continue
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("coordinates")
            except ValueError:
                invalid["coordinates"] += 1
            try:
                acquired = date.fromisoformat(row["acq_date"])
                years[str(acquired.year)] += 1
                first = min(first, acquired) if first else acquired
                last = max(last, acquired) if last else acquired
            except ValueError:
                invalid["date"] += 1
            time = row["acq_time"].strip()
            if not time.isdigit() or len(time) > 4 or int(time) > 2359 or int(time) % 100 > 59:
                invalid["time"] += 1
            version = row["version"].strip()
            versions[version or "unavailable"] += 1
            kind = row.get("type", "").strip() if has_type else ""
            if kind in {"0", "1", "2", "3"}: counts["type_" + kind] += 1
            elif not kind: counts["type_unavailable"] += 1
            else: invalid["type"] += 1
    return {"artifact_kind":"firepulse-nrt-preflight", "schema_version":1, "input_name":path.name, "input_sha256":digest,
            "type_column_present":has_type, "counts":dict(sorted(counts.items())), "invalid":dict(sorted(invalid.items())),
            "versions":dict(sorted(versions.items())), "years":dict(sorted(years.items())), "first_date":first.isoformat() if first else None, "last_date":last.isoformat() if last else None,
            "limitations":["NRT or standard processing must be confirmed from product provenance, not inferred solely from a filename or numerical version.", "Country geometry, observation coverage, duplicate detections, and source authenticity have not been verified.", "Preflight does not normalize data or import it to a database."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); report=inspect_csv(args.input)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report,stream,indent=2,sort_keys=True); stream.write("\n")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 1 if report["invalid"] else 0


if __name__ == "__main__": raise SystemExit(main())
