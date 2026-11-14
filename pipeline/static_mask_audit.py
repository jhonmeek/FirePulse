"""Audit the M2 persistent-cell mask against normalized FIRMS observations.

This reproduces M2's current 0.05-degree rule for measurement only; it does
not publish a filtered dataset or assert that flagged cells are not fires.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

GRID_DEG = 0.05
TYPE23_MIN = 20
SNPP_MONTHS_MIN = 48


def audit(input_dir: Path, output_dir: Path) -> dict:
    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_kind") != "firepulse-normalized" or manifest.get("schema_version") != 1:
        raise ValueError("unrecognized normalized manifest")

    cells: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"rows": 0, "type0": 0, "type23": 0, "snpp_months": set(), "sources": Counter(), "years": Counter()}
    )
    input_hashes = []
    rows_total = 0
    for entry in manifest["files"]:
        name = entry["output_file"]
        path = (input_dir / name).resolve()
        if path.parent != input_dir.resolve() or not path.is_file():
            raise ValueError(f"invalid or missing normalized input: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["output_sha256"]:
            raise ValueError(f"normalized input checksum mismatch: {name}")
        input_hashes.append({"file": name, "sha256": digest})
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                # M2 uses SQL FLOOR, including for negative coordinates.
                key = (math.floor(lat * 20), math.floor(lon * 20))
                cell = cells[key]
                cell["rows"] += 1
                cell["type0"] += row["hotspot_type"] == "0"
                cell["type23"] += row["hotspot_type"] in {"2", "3"}
                cell["sources"][row["source"]] += 1
                cell["years"][row["acquired_at"][:4]] += 1
                if row["source"] == "viirs-snpp":
                    cell["snpp_months"].add(row["acquired_at"][:7])
                rows_total += 1

    flagged = {
        key: cell
        for key, cell in cells.items()
        if cell["type23"] >= TYPE23_MIN or len(cell["snpp_months"]) >= SNPP_MONTHS_MIN
    }
    flagged_type = Counter()
    flagged_source = Counter()
    flagged_year = Counter()
    for cell in flagged.values():
        flagged_source.update(cell["sources"])
        flagged_year.update(cell["years"])
        flagged_type["type0"] += cell["type0"]
        flagged_type["all"] += cell["rows"]

    all_type0 = sum(cell["type0"] for cell in cells.values())
    cell_rows = []
    for (lat_i, lon_i), cell in sorted(flagged.items()):
        cell_rows.append({
            "lat0": f"{lat_i / 20:.2f}", "lon0": f"{lon_i / 20:.2f}",
            "type23_count": cell["type23"], "active_months_snpp": len(cell["snpp_months"]),
            "reason": "type23_and_snpp" if cell["type23"] >= TYPE23_MIN and len(cell["snpp_months"]) >= SNPP_MONTHS_MIN else "type23_threshold" if cell["type23"] >= TYPE23_MIN else "snpp_persistence",
            "all_detections": cell["rows"], "type0_detections": cell["type0"],
            "detections_by_source": json.dumps(dict(sorted(cell["sources"].items())), sort_keys=True),
        })

    result = {
        "schema_version": 1, "artifact_kind": "firepulse-static-mask-audit",
        "grid_deg": GRID_DEG, "type23_min": TYPE23_MIN, "snpp_active_months_min": SNPP_MONTHS_MIN,
        "criterion_period": "all normalized archive rows; retrospective and not independent validation",
        "scope": "GA country files; geometry unverified",
        "input_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "inputs": input_hashes, "input_rows": rows_total, "occupied_cells": len(cells),
        "flagged_cells": len(flagged), "all_detections": rows_total,
        "detections_in_flagged_cells": flagged_type["all"],
        "detections_in_flagged_cells_by_source": dict(sorted(flagged_source.items())),
        "type0_total": all_type0, "type0_in_flagged_cells": flagged_type["type0"],
        "type0_fraction_in_flagged_cells": flagged_type["type0"] / all_type0 if all_type0 else None,
        "detections_in_flagged_cells_by_year": dict(sorted(flagged_year.items())),
        "limitations": [
            "A flagged cell is a candidate persistent thermal source, not proof of an industrial flare.",
            "The retrospective mask uses the full 2000-2025 archive, so it is not a prospective or held-out estimate.",
            "The coarse 0.05-degree cell can include nearby vegetation fires; this audit measures exposure, not false-positive rate.",
            "The rule is reproduced from M2 SQL and evaluated on country files, not M2's database spatial subset.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "static_mask_cells.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cell_rows[0]) if cell_rows else ["lat0", "lon0", "type23_count", "active_months_snpp", "reason", "all_detections", "type0_detections", "detections_by_source"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(cell_rows)
    (output_dir / "static_mask_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/normalized"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/static-mask-audit"))
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.input, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
