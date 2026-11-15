"""Compare type-0 models with a training-period mask inside PostGIS GA."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from pipeline.temporal_experiment import run


def experiment(calendar: Path, manifest: Path, sql_csv: Path):
    raw=calendar.read_bytes(); meta=json.loads(manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest()!=meta.get("calendar_sha256"): raise ValueError("calendar checksum mismatch")
    counts={}
    with sql_csv.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            key=(row["month"],row["source"],row["satellite"])
            if key in counts: raise ValueError("duplicate SQL row")
            raw_count, type0, kept, removed=(int(row[k]) for k in ("raw_count","type0_count","type0_unmasked_count","type0_masked_count"))
            if min(raw_count,type0,kept,removed)<0 or kept+removed!=type0 or type0>raw_count: raise ValueError("invalid mask reconciliation")
            counts[key]=(raw_count,type0,kept)
    results={}
    with tempfile.TemporaryDirectory(prefix="ga-frozen-") as tmp:
        for variant, idx in (("type0_without_mask",1),("type0_with_mask",2)):
            payload=json.loads(raw)
            for row in payload["rows"]:
                key=(row["month"],row["source"],row["satellite"])
                if key in counts:
                    row["count_raw"]=counts[key][idx]
                elif row["count_raw"] is not None:
                    # Missing SQL group is not proof of a valid zero or coverage.
                    row["count_raw"]=None; row["status"]="missing_input"
            root=Path(tmp); c=root/"calendar.json"; m=root/"manifest.json"
            encoded=(json.dumps(payload,sort_keys=True)+"\n").encode("utf-8"); c.write_bytes(encoded)
            m.write_text(json.dumps({"calendar_sha256":hashlib.sha256(encoded).hexdigest()}),encoding="utf-8")
            results[variant]=run(c,m)
            results[variant]["limitations"][0]="GA ST_Within PostGIS, based on local database and geometry"
            results[variant]["limitations"][1]="type-0 counts; " + ("mask fitted to training GA observations" if idx==2 else "no mask")
    return {"artifact_kind":"firepulse-postgis-frozen-experiment","schema_version":1,
            "calendar_sha256":hashlib.sha256(raw).hexdigest(),"postgis_csv_sha256":hashlib.sha256(sql_csv.read_bytes()).hexdigest(),
            "mask_training":"2012-02 through 2016-12 UTC", "variants":results,
            "limitations":["PostGIS source and geometry must be verified when reproduced.","Mask thresholds are inherited and unvalidated for this short training period.","Country calendar status defines eligibility; observational coverage remains unknown.","2023-2025 already examined; not a blind final evaluation."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    p.add_argument("--manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    p.add_argument("--postgis-csv",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=experiment(a.calendar,a.manifest,a.postgis_csv)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:v["evaluation"] for k,v in result["variants"].items()},indent=2))


if __name__=="__main__": main()
