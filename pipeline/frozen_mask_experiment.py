"""Compare type-0 monthly counts with a mask learned only in 2012-02..2016-12."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.temporal_experiment import run

START, END = "2012-02", "2016-12"


def build_mask(observations):
    cells = defaultdict(lambda: {"type23": 0, "months": set()})
    for row in observations:
        month = row["acquired_at"][:7]
        if START <= month <= END:
            cell = (math.floor(float(row["latitude"]) * 20), math.floor(float(row["longitude"]) * 20))
            cells[cell]["type23"] += row["hotspot_type"] in {"2", "3"}
            if row["source"] == "viirs-snpp": cells[cell]["months"].add(month)
    return {cell for cell, values in cells.items() if values["type23"] >= 20 or len(values["months"]) >= 48}


def experiment(normalized: Path, calendar: Path, monthly_manifest: Path) -> dict:
    manifest_bytes = (normalized / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("artifact_kind") != "firepulse-normalized" or manifest.get("schema_version") != 1:
        raise ValueError("invalid normalized manifest")
    original = calendar.read_bytes()
    monthly = json.loads(monthly_manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(manifest_bytes).hexdigest() != monthly.get("normalized_manifest_sha256"):
        raise ValueError("monthly calendar was built from another normalized manifest")
    if hashlib.sha256(original).hexdigest() != monthly["calendar_sha256"]:
        raise ValueError("calendar checksum mismatch")
    entries = manifest["files"]
    paths = []
    for entry in entries:
        path = (normalized / entry["output_file"]).resolve()
        if path.parent != normalized.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["output_sha256"]:
            raise ValueError("normalized input missing, unsafe or modified")
        paths.append(path)

    def observations():
        for path in paths:
            with path.open(encoding="utf-8", newline="") as stream:
                yield from csv.DictReader(stream)

    mask = build_mask(observations())
    counts = {"unmasked": Counter(), "masked": Counter()}
    removed = Counter()
    for row in observations():
        if row["hotspot_type"] != "0": continue
        month = row["acquired_at"][:7]
        key = (month, row["source"], row["satellite"])
        cell = (math.floor(float(row["latitude"]) * 20), math.floor(float(row["longitude"]) * 20))
        counts["unmasked"][key] += 1
        if cell not in mask: counts["masked"][key] += 1
        else: removed[row["source"]] += 1

    results = {}
    with tempfile.TemporaryDirectory(prefix="firepulse-m1-mask-") as tmp:
        root = Path(tmp)
        for variant in ("unmasked", "masked"):
            payload = json.loads(original)
            for row in payload["rows"]:
                if row["count_raw"] is not None:
                    row["count_raw"] = counts[variant][(row["month"], row["source"], row["satellite"])]
            encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
            cal = root / "calendar.json"; meta = root / "manifest.json"
            cal.write_bytes(encoded)
            meta.write_text(json.dumps({"calendar_sha256": hashlib.sha256(encoded).hexdigest()}), encoding="utf-8")
            results[variant] = run(cal, meta)
            results[variant]["limitations"][1] = "Type-0 counts; mask frozen at end of training" if variant == "masked" else "Type-0 counts; no static mask"
    return {"artifact_kind": "firepulse-frozen-mask-experiment", "schema_version": 1,
            "period": [START, END], "grid_deg": 0.05, "thresholds": {"type23": 20, "snpp_months": 48},
            "flagged_cells": len(mask), "excluded_type0_by_source_all_years": dict(sorted(removed.items())),
            "normalized_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "source_calendar_sha256": hashlib.sha256(original).hexdigest(), "variants": results,
            "limitations": ["Thresholds are inherited from M2 and not calibrated to this shorter training period.", "Cell membership uses half-open floor cells; M2 uses ST_Intersects including boundaries.", "Retrospective archive versions and unknown observation coverage remain limitations.", "Prior knowledge of test years prevents a blind final test."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--normalized", type=Path, default=Path("data/processed/normalized"))
    p.add_argument("--calendar", type=Path, default=Path("data/processed/monthly/calendar.json"))
    p.add_argument("--monthly-manifest", type=Path, default=Path("data/processed/monthly/manifest.json"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); result = experiment(args.normalized, args.calendar, args.monthly_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"flagged_cells": result["flagged_cells"], "variants": {k: v["evaluation"] for k,v in result["variants"].items()}}, indent=2))


if __name__ == "__main__": main()
