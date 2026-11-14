"""Prepare a supplied 2026 FIRMS NRT CSV without filling unobserved months."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from pipeline.nrt_preflight import inspect_csv


def prepare(source: Path, product: str) -> dict:
    if product not in {"VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"}:
        raise ValueError("unsupported product")
    check = inspect_csv(source)
    if check["invalid"] or not check["counts"].get("rows"):
        raise ValueError("input failed preflight or is empty")
    if set(check["years"]) != {"2026"}:
        raise ValueError("only 2026 observations are accepted")
    # Product is caller-supplied provenance; it is not verified by the CSV alone.
    monthly = Counter()
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            kind = (row.get("type") or "").strip() or "unavailable"
            monthly[(row["acq_date"][:7], kind)] += 1
    return {"artifact_kind": "firepulse-nrt-2026-preparation", "schema_version": 1,
            "source_product_declared": product, "source_product_verified": False,
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_file": source.name, "preflight": check,
            "monthly_type_counts": [{"month": month, "type_nasa": kind, "detection_count": count}
                                    for (month, kind), count in sorted(monthly.items())],
            "limitations": ["Only recorded detections are counted; absent months are unknown, not zero.",
                            "Declared NRT product, geographic scope and observation coverage require independent validation.",
                            "No MODIS-VIIRS harmonization, deduplication or database import is performed."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = prepare(args.input, args.product)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, sort_keys=True); stream.write("\n")
    print(f"Prepared {data['preflight']['counts']['rows']} detections; NRT provenance requires validation")
    return 0


if __name__ == "__main__": raise SystemExit(main())
