"""Reconcile country-file calendar with direct monthly observation counts from PostGIS."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from pipeline.temporal_experiment import run


def compare(calendar: Path, manifest: Path, direct_csv: Path):
    raw = calendar.read_bytes()
    source_meta = json.loads(manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != source_meta.get("calendar_sha256"):
        raise ValueError("calendar checksum mismatch")
    direct = {}
    with direct_csv.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["month"], row["source"], row["satellite"])
            if key in direct: raise ValueError("duplicate PostGIS month/platform")
            country, ga = int(row["country_count"]), int(row["ga_count"])
            if country < ga or ga < 0: raise ValueError("invalid spatial count")
            direct[key] = (country, ga)
    payload = json.loads(raw); mismatches = []; used = set(); totals = {}; calendar_keys = set()
    for row in payload["rows"]:
        key = (row["month"], row["source"], row["satellite"])
        if key in calendar_keys: raise ValueError("duplicate calendar month/platform")
        calendar_keys.add(key)
        if key not in direct:
            if row["count_raw"] not in (None, 0): mismatches.append({"key": key, "m1": row["count_raw"], "postgis": None})
            continue
        used.add(key); country, ga = direct[key]
        if row["count_raw"] != country:
            mismatches.append({"key": key, "m1": row["count_raw"], "postgis": country})
        totals[row["source"]] = totals.get(row["source"], 0) + country-ga
        row["count_raw"] = ga
    extra = set(direct)-used
    if mismatches or extra: raise ValueError(f"country input does not match PostGIS: {len(mismatches)} mismatches and {len(extra)} extra keys")
    with tempfile.TemporaryDirectory(prefix="firepulse-ga-") as tmp:
        root = Path(tmp); cal = root/"calendar.json"; meta = root/"manifest.json"
        encoded = (json.dumps(payload,sort_keys=True)+"\n").encode("utf-8")
        cal.write_bytes(encoded); meta.write_text(json.dumps({"calendar_sha256":hashlib.sha256(encoded).hexdigest()}),encoding="utf-8")
        ga_result = run(cal,meta)
    ga_result["limitations"][0] = "GA counts use the local PostGIS ST_Within geometry; database and geometry provenance must be independently verified."
    country_result = run(calendar,manifest)
    return {"artifact_kind":"firepulse-postgis-direct-comparison","schema_version":1,
            "m1_calendar_sha256":hashlib.sha256(raw).hexdigest(),"postgis_csv_sha256":hashlib.sha256(direct_csv.read_bytes()).hexdigest(),
            "direct_rows":len(direct),"country_mismatches":len(mismatches),"outside_ga_by_source":totals,
            "country_experiment":country_result,"ga_experiment":ga_result,
            "limitations":["Direct SQL counts detections strictly ST_Within GA; geometry and database versions must be recorded externally.","No observational coverage verification: eligible months preserve country-file statuses for both experiments.","2023-2025 was previously inspected and is not a blind final holdout.","Unmasked raw detections; no frozen mask or NRT evaluation."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    parser.add_argument("--manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    parser.add_argument("--postgis-csv",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); result=compare(args.calendar,args.manifest,args.postgis_csv)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"direct_rows":result["direct_rows"],"outside_ga_by_source":result["outside_ga_by_source"],"country":result["country_experiment"]["evaluation"],"ga":result["ga_experiment"]["evaluation"]},indent=2))


if __name__ == "__main__": main()
