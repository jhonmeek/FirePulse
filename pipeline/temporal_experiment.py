"""Exploratory chronological validation on the M1 country-file monthly calendar."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

WINDOWS = {"train": ("2012-02", "2016-12"), "select": ("2017-01", "2019-12"), "calibrate": ("2020-01", "2022-12"), "evaluate": ("2023-01", "2025-12")}


def metrics(pred, truth):
    errors = [a-b for a,b in zip(pred,truth)]
    mean = sum(truth)/len(truth)
    sst = sum((v-mean)**2 for v in truth)
    return {"n":len(truth), "mae":sum(abs(e) for e in errors)/len(errors), "rmse":math.sqrt(sum(e*e for e in errors)/len(errors)), "bias":sum(errors)/len(errors), "r2":1-sum(e*e for e in errors)/sst if sst else None}


def fit(xs, ys):
    lx=[math.log1p(x) for x in xs]; ly=[math.log1p(y) for y in ys]
    mx=sum(lx)/len(lx); my=sum(ly)/len(ly)
    den=sum((v-mx)**2 for v in lx)
    if den == 0: raise ValueError("MODIS training values have zero variance")
    p=sum((x-mx)*(y-my) for x,y in zip(lx,ly))/den
    return p, my-p*mx


def month_range(start, end):
    year, month = map(int, start.split("-"))
    while (year, month) <= tuple(map(int, end.split("-"))):
        yield f"{year:04d}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def run(calendar: Path, manifest: Path):
    raw=calendar.read_bytes(); metadata=json.loads(manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest()!=metadata.get("calendar_sha256"): raise ValueError("calendar checksum mismatch")
    data=json.loads(raw); months=defaultdict(dict)
    for row in data["rows"]:
        months[row["month"]][(row["source"],row["satellite"])]=row
    windows={}; excluded={}
    keys=(("modis","Terra"),("modis","Aqua"),("viirs-snpp","N"))
    for label,(start,end) in WINDOWS.items():
        windows[label]=[]; excluded[label]=[]
        for month in month_range(start,end):
            rows=[months[month].get(k) for k in keys]
            if any(r is None or r.get("status")!="observed_detections_recorded" or r.get("count_raw") is None for r in rows):
                excluded[label].append(month); continue
            windows[label].append((month,rows[0]["count_raw"]+rows[1]["count_raw"],rows[2]["count_raw"]))
        if not windows[label]: raise ValueError(f"no eligible months in {label}")
    train=windows["train"]; select=windows["select"]
    p,q=fit([r[1] for r in train],[r[2] for r in train])
    alpha=sum(r[2] for r in train)/sum(r[1] for r in train)
    candidates={"identity":lambda x:x,"ratio":lambda x:alpha*x,"power":lambda x:max(0,math.expm1(p*math.log1p(x)+q))}
    scores={name:metrics([fn(x) for _,x,y in select],[y for _,x,y in select]) for name,fn in candidates.items()}
    winner=min(sorted(scores),key=lambda name:scores[name]["mae"])
    fn=candidates[winner]; cal=windows["calibrate"]; test=windows["evaluate"]
    residuals=sorted(abs(y-fn(x)) for _,x,y in cal)
    rank=min(len(residuals),math.ceil((len(residuals)+1)*0.8)); radius=residuals[rank-1]
    values=[y for _,x,y in test]; preds=[fn(x) for _,x,y in test]
    covered=sum(max(0,pred-radius)<=y<=pred+radius for pred,y in zip(preds,values))
    return {"artifact_kind":"firepulse-m1-temporal-experiment","schema_version":1,"calendar_sha256":hashlib.sha256(raw).hexdigest(),"windows":WINDOWS,"eligible_months":{k:len(v) for k,v in windows.items()},"excluded_months":excluded,"fit":{"power_p":p,"power_q":q,"ratio":alpha},"selection_metrics":scores,"selected_model":winner,"interval":{"calibration_rank":rank,"radius_count_units":radius,"nominal_level":0.8},"evaluation":{"metrics":metrics(preds,values),"covered":covered,"coverage":covered/len(test),"mean_width":sum(pred+radius-max(0,pred-radius) for pred in preds)/len(preds)},"limitations":["Country file geometry is unverified; M2 PostGIS values are not directly comparable.","Unmasked observations; no frozen static mask has been evaluated.","Observation coverage unknown; requiring observed_detections_recorded for each platform may introduce selection bias.","2023-2025 was previously inspected, not a blind final holdout.","Time dependence invalidates an automatic exchangeability coverage guarantee.","NOAA-20 bridge and custom-region uncertainty not evaluated."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    parser.add_argument("--manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); result=run(args.calendar,args.manifest)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__": main()
