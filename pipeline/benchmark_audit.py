"""Independently reproduce M2 benchmark metrics from its calibration CSV export."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def _metrics(predicted: list[float], actual: list[float]) -> dict:
    errors = [p - y for p, y in zip(predicted, actual)]
    mean = sum(actual) / len(actual)
    sst = sum((y - mean) ** 2 for y in actual)
    return {
        "mae": round(sum(abs(e) for e in errors) / len(errors), 2),
        "rmse": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 2),
        "bias": round(sum(errors) / len(errors), 2),
        "r2": round(1 - sum(e * e for e in errors) / sst, 4) if sst else 0.0,
    }


def audit(csv_path: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if digest != manifest.get("csv_sha256"):
        raise ValueError("M2 calibration CSV SHA-256 does not match manifest")
    grouped = defaultdict(lambda: {"train": [], "test": []})
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            split = row["calibration_split"]
            if split not in {"train", "test"}:
                continue
            if row["region"] == "GA":
                grouped[row["filter_static"]][split].append(row)

    results = []
    for filter_static, split in sorted(grouped.items()):
        train, test = split["train"], split["test"]
        if not train or not test:
            raise ValueError(f"missing train/test rows for filter_static={filter_static}")
        x = [float(r["modis_count"] or 0) for r in train]
        y = [float(r["viirs_snpp_count"] or 0) for r in train]
        lx, ly = [math.log1p(v) for v in x], [math.log1p(v) for v in y]
        mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
        denom = sum((v - mx) ** 2 for v in lx)
        p = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / denom if denom else 1.0
        q = my - p * mx
        xt = [float(r["modis_count"] or 0) for r in test]
        yt = [float(r["viirs_snpp_count"] or 0) for r in test]
        predictions = [max(0.0, math.expm1(p * math.log1p(v) + q)) for v in xt]
        interval_rows = [r for r in test if r["ci_low"] not in ("", None) and r["ci_high"] not in ("", None) and r["viirs_snpp_count"] not in ("", None)]
        covered = sum(float(r["ci_low"]) <= float(r["viirs_snpp_count"]) <= float(r["ci_high"]) for r in interval_rows)
        results.append({
            "region": "GA", "filter_static": filter_static,
            "train_months": len(train), "test_months": len(test),
            "refit_power_law_p": round(p, 4), "refit_power_law_q": round(q, 4),
            "recomputed_test_metrics": _metrics(predictions, yt),
            "exported_test_metrics": next(run["metrics"]["models_out_of_sample"]["power_law_log1p"] for run in manifest["runs"] if run["region"] == "GA" and str(run["filter_static"]).lower() == filter_static),
            "test_interval_coverage": covered / len(interval_rows) if interval_rows else None,
            "test_interval_covered_months": covered,
            "test_interval_evaluable_months": len(interval_rows),
            "interval_coverage_is_independent": False,
        })
    return {
        "schema_version": 1,
        "artifact_kind": "firepulse-m1-benchmark-audit",
        "m2_csv_sha256": digest,
        "m2_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "db_provenance": manifest.get("db_provenance"),
        "results": results,
        "interpretation": "Exact reproduction checks the exported monthly counts and the power-law fit/metrics. Test interval coverage is descriptive only because M2 calibrated the interval quantile on this same test window.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit(args.csv, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
