"""Produce monthly exclusive FIRMS type counts from verified normalized archives."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

TYPE_CODES = ("0", "1", "2", "3", "unavailable")


def build(normalized: Path, calendar: Path, monthly_manifest: Path) -> dict:
    normal_manifest = (normalized / "manifest.json").read_bytes()
    normal = json.loads(normal_manifest)
    monthly = json.loads(monthly_manifest.read_text(encoding="utf-8"))
    raw_cal = calendar.read_bytes()
    if normal.get("artifact_kind") != "firepulse-normalized" or normal.get("schema_version") != 1:
        raise ValueError("unrecognized normalized manifest")
    if hashlib.sha256(normal_manifest).hexdigest() != monthly.get("normalized_manifest_sha256"):
        raise ValueError("calendar does not reference this normalized manifest")
    if hashlib.sha256(raw_cal).hexdigest() != monthly.get("calendar_sha256"):
        raise ValueError("calendar checksum mismatch")
    counts = Counter(); seen = set(); total = 0
    for entry in normal["files"]:
        name = entry["output_file"]; path = (normalized / name).resolve()
        if path.parent != normalized.resolve() or name in seen or not path.is_file():
            raise ValueError("invalid or duplicate normalized input")
        seen.add(name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["output_sha256"]:
            raise ValueError("normalized CSV checksum mismatch")
        file_count = 0
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                kind = row.get("hotspot_type", "").strip() or "unavailable"
                if kind not in TYPE_CODES: raise ValueError("unknown NASA type")
                key=(row["acquired_at"][:7],row["source"],row["satellite"],kind)
                counts[key]+=1; file_count+=1
        if file_count != entry["output_rows"]: raise ValueError("normalized row count mismatch")
        total+=file_count
    result=[]; reconciled=0
    for row in json.loads(raw_cal)["rows"]:
        key=(row["month"],row["source"],row["satellite"])
        if row["count_raw"] is None:
            values={kind:None for kind in TYPE_CODES}
        else:
            values={kind:counts[key+(kind,)] for kind in TYPE_CODES}
            if sum(values.values()) != row["count_raw"]: raise ValueError(f"type count mismatch for {key}")
            reconciled+=sum(values.values())
        result.append({"region":row["region"],"dataset_scope":row["dataset_scope"],"month":row["month"],"source":row["source"],"satellite":row["satellite"],"status":row["status"],"observation_coverage":row["observation_coverage"],"type_counts":values,"persistent_cell_indicator":"not_evaluated"})
    if reconciled != total: raise ValueError("calendar and observation totals differ")
    return {"artifact_kind":"firepulse-monthly-types","schema_version":1,"input_rows":total,"calendar_sha256":hashlib.sha256(raw_cal).hexdigest(),"normalized_manifest_sha256":hashlib.sha256(normal_manifest).hexdigest(),"rows":result,"limitations":["Raw detections, not distinct fires or harmonized series.","The country-file geography is not verified against PostGIS.","Current historical normalizer requires a NASA type; missing-type NRT ingestion is not implemented.","Persistent cell membership has not been evaluated in this output."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--normalized",type=Path,default=Path("data/processed/normalized"))
    p.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    p.add_argument("--monthly-manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=build(a.normalized,a.calendar,a.monthly_manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(f"Reconciled {result['input_rows']} detections, {len(result['rows'])} month/platform rows")


if __name__ == "__main__": main()
