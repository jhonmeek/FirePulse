"""Compare M1 country-file counts to the unmasked M2 GA PostGIS export."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCES = {("modis", "Terra"): "modis_terra_count", ("modis", "Aqua"): "modis_aqua_count", ("viirs-snpp", "N"): "viirs_snpp_count", ("viirs-noaa20", "N20"): "viirs_noaa20_count"}


def compare(calendar_path: Path, monthly_manifest: Path, export_path: Path, export_manifest: Path):
    calendar_bytes = calendar_path.read_bytes()
    export_bytes = export_path.read_bytes()
    m1_meta = json.loads(monthly_manifest.read_text(encoding="utf-8"))
    m2_meta = json.loads(export_manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(calendar_bytes).hexdigest() != m1_meta.get("calendar_sha256"):
        raise ValueError("M1 calendar checksum mismatch")
    if hashlib.sha256(export_bytes).hexdigest() != m2_meta.get("csv_sha256"):
        raise ValueError("M2 export checksum mismatch")
    if m2_meta.get("artifact_kind") != "firepulse-m2-calibration-series":
        raise ValueError("unexpected M2 manifest")
    m2 = {}
    with export_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["region"] == "GA" and row["filter_static"].lower() == "false":
                if row["month"] in m2: raise ValueError("duplicate GA unfiltered month")
                m2[row["month"]] = row
    records = []
    totals = Counter()
    for row in json.loads(calendar_bytes)["rows"]:
        source = (row["source"], row["satellite"])
        if source not in SOURCES: continue
        m2_row = m2.get(row["month"])
        raw = m2_row.get(SOURCES[source], "") if m2_row else ""
        value = int(raw) if raw not in (None, "") else None
        original = row.get("count_raw")
        difference = original - value if original is not None and value is not None else None
        if difference is not None:
            totals[row["source"] + "_outside_or_difference"] += difference
            totals[row["source"] + "_matched_rows"] += 1
        records.append({"month": row["month"], "source": row["source"], "satellite": row["satellite"], "m1_count": original, "m1_status": row["status"], "m2_count": value, "difference": difference})
    return {"artifact_kind":"firepulse-m1-m2-monthly-comparison", "schema_version":1, "m1_calendar_sha256":hashlib.sha256(calendar_bytes).hexdigest(), "m2_csv_sha256":hashlib.sha256(export_bytes).hexdigest(), "totals":dict(sorted(totals.items())), "rows":records, "limitations":["M1 uses country files without verified boundary; M2 uses PostGIS GA ST_Within.", "M2 export fills some missing observations with zero; source-month coverage is not independently established.", "Differences can include boundary, ingestion, processing and zero-filling effects; they are not automatically counts of points outside the polygon."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    parser.add_argument("--monthly-manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    parser.add_argument("--export",type=Path,required=True)
    parser.add_argument("--export-manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); result=compare(args.calendar,args.monthly_manifest,args.export,args.export_manifest)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(result["totals"],indent=2,sort_keys=True))


if __name__ == "__main__": main()
