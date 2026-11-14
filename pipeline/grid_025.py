"""Create reproducible monthly 0.25-degree FIRMS grids with mask variants."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def build_grid(input_dir: Path, mask_dir: Path, output_dir: Path) -> dict:
    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_kind") != "firepulse-normalized" or manifest.get("schema_version") != 1:
        raise ValueError("unrecognized normalized manifest")
    mask_path = mask_dir / "static_mask_audit.json"
    mask = json.loads(mask_path.read_text(encoding="utf-8"))
    if mask.get("artifact_kind") != "firepulse-static-mask-audit":
        raise ValueError("unrecognized static mask audit")
    masked = set()
    with (mask_dir / "static_mask_cells.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            masked.add((math.floor(float(row["lat0"]) * 20), math.floor(float(row["lon0"]) * 20)))

    counts: Counter = Counter()
    input_hashes = []
    row_total = 0
    for entry in manifest["files"]:
        path = input_dir / entry["output_file"]
        if path.resolve().parent != input_dir.resolve() or not path.is_file():
            raise ValueError(f"invalid or missing input {entry['output_file']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["output_sha256"]:
            raise ValueError(f"normalized input checksum mismatch: {path.name}")
        input_hashes.append({"file": path.name, "sha256": digest})
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                lat, lon = float(row["latitude"]), float(row["longitude"])
                cell005 = (math.floor(lat * 20), math.floor(lon * 20))
                cell025 = (math.floor(lat * 4), math.floor(lon * 4))
                key = (row["acquired_at"][:7], row["source"], row["satellite"], *cell025)
                counts[key + ("raw",)] += 1
                if row["hotspot_type"] == "0":
                    counts[key + ("type0",)] += 1
                    if cell005 not in masked:
                        counts[key + ("type0_unmasked",)] += 1
                if cell005 in masked:
                    counts[key + ("in_static_mask",)] += 1
                row_total += 1

    rows = []
    keys = sorted({key[:5] for key in counts})
    for key in keys:
        item = dict(zip(("month", "source", "satellite"), key[:3]))
        item["lat0"] = f"{key[3] / 4:.2f}"
        item["lon0"] = f"{key[4] / 4:.2f}"
        item["count_raw"] = counts[key + ("raw",)]
        item["count_type0"] = counts[key + ("type0",)]
        item["count_type0_unmasked"] = counts[key + ("type0_unmasked",)]
        item["count_in_static_mask"] = counts[key + ("in_static_mask",)]
        rows.append(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ["month", "source", "satellite", "lat0", "lon0", "count_raw", "count_type0", "count_type0_unmasked", "count_in_static_mask"]
    with (output_dir / "grid_025_monthly.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    calendar = {"schema_version": 1, "artifact_kind": "firepulse-grid-025-monthly", "grid_deg": 0.25, "mask_grid_deg": 0.05, "static_mask_audit_sha256": hashlib.sha256(mask_path.read_bytes()).hexdigest(), "rows": rows}
    (output_dir / "grid_025_monthly.json").write_text(json.dumps(calendar, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    result = {"schema_version": 1, "artifact_kind": "firepulse-grid-025", "grid_deg": 0.25, "input_rows": row_total, "grid_month_rows": len(rows), "normalized_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "static_mask_audit_sha256": hashlib.sha256(mask_path.read_bytes()).hexdigest(), "inputs": input_hashes, "csv_sha256": hashlib.sha256((output_dir / "grid_025_monthly.csv").read_bytes()).hexdigest(), "json_sha256": hashlib.sha256((output_dir / "grid_025_monthly.json").read_bytes()).hexdigest(), "scope": "GA country files; geometry unverified", "coverage": "observation coverage unknown; absent rows are not zero coverage"}
    (output_dir / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/normalized"))
    parser.add_argument("--mask", type=Path, default=Path("data/processed/static-mask-audit"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/grid-025"))
    args = parser.parse_args(argv)
    print(json.dumps(build_grid(args.input, args.mask, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
