"""Create deterministic, bounded monthly national count outputs."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,tempfile
from collections import Counter
from datetime import date
from pathlib import Path

STARTS={"modis":date(2000,11,1),"modis-aqua":date(2002,7,1),"viirs-snpp":date(2012,1,20),"viirs-noaa20":date(2018,4,1)}
SATS={"modis":["Terra","Aqua"],"viirs-snpp":["N"],"viirs-noaa20":["N20"]}
PRODUCT={"modis":"modis","viirs-snpp":"viirs-snpp","viirs-noaa20":"viirs-jpss1"}
FIELDS=["region","dataset_scope","month","source","satellite","count_raw","count_type0_candidate","harmonized_value","status","observation_coverage"]

def _month_range():
    y,m=2000,11
    while (y,m)<=(2025,12):
        yield f"{y:04d}-{m:02d}"; y,m=(y+1,1) if m==12 else (y,m+1)

def _recognized_manifest(src):
    try: manifest=json.loads((src/"manifest.json").read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ValueError("normalized input manifest missing or invalid") from exc
    if manifest.get("schema_version")!=1 or manifest.get("artifact_kind")!="firepulse-normalized": raise ValueError("unrecognized normalized manifest")
    return manifest

def aggregate(input_dir:Path,output_dir:Path):
    src,dst=input_dir.resolve(),output_dir.resolve()
    if not src.is_dir() or src==dst or src in dst.parents or dst in src.parents: raise ValueError("invalid input/output directories")
    manifest=_recognized_manifest(src); entries=manifest.get("files",[])
    if not entries: raise ValueError("normalization manifest has no source files")
    expected=set(); hashes={}; totals=Counter()
    for e in entries:
        name=e.get("output_file"); product=e.get("product"); year=e.get("year")
        if not isinstance(name,str) or Path(name).name!=name or name in {".",".."} or "/" in name or "\\" in name or product not in PRODUCT or not isinstance(year,int): raise ValueError("invalid normalized manifest entry")
        if name in expected: raise ValueError("duplicate normalized manifest filename")
        expected.add(name); p=src/name
        if not p.is_file(): raise ValueError(f"normalized input missing: {name}")
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=e.get("output_sha256"): raise ValueError(f"normalized input hash mismatch: {name}")
        hashes[name]=digest
    actual={p.name for p in src.glob("*_normalized.csv")}
    if actual!=expected: raise ValueError(f"normalized file inventory mismatch; missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    # Product/year presence is known from the manifest; the local annual file controls missing_input vs zero detections.
    present={(e["product"],e["year"]):e for e in entries}
    counts=Counter(); type0=Counter(); years_seen=Counter()
    for e in entries:
        name=e["output_file"]; product=e["product"]; year=e["year"]
        file_count=0
        with (src/name).open(encoding="utf-8",newline="") as f:
            reader=csv.DictReader(f)
            for r in reader:
                if r.get("source")!=product: raise ValueError(f"source mismatch in {name}")
                file_count+=1
                m=r["acquired_at"][:7]; sat=r.get("satellite","")
                if m<"2000-11" or m>"2025-12": raise ValueError(f"date outside aggregation horizon in {name}: {m}")
                key=(m,product,sat); counts[key]+=1; years_seen[(product,year)]+=1
                if r.get("hotspot_type")=="0": type0[key]+=1
        if file_count!=e.get("output_rows") or file_count!=e.get("input_rows"): raise ValueError(f"row reconciliation failed for {name}")
    if sum(counts.values())!=manifest.get("input_rows"): raise ValueError("input/output row reconciliation failed")
    if sum(type0.values())>sum(counts.values()): raise ValueError("type 0 reconciliation failed")
    rows=[]
    for product,satellites in SATS.items():
        for sat in satellites:
            for month in _month_range():
                y,mo=map(int,month.split("-")); dt=date(y,mo,1); key=(month,product,sat)
                common={"region":"GA","dataset_scope":"country_file_unverified_geometry","month":month,"source":product,"satellite":sat}
                start=STARTS["modis-aqua"] if product=="modis" and sat=="Aqua" else STARTS[product]
                available=(dt.year,dt.month)>=(start.year,start.month)
                if not available: row={**common,"count_raw":None,"count_type0_candidate":None,"harmonized_value":None,"status":"not_available","observation_coverage":"unknown"}
                elif (product,y) not in present: row={**common,"count_raw":None,"count_type0_candidate":None,"harmonized_value":None,"status":"missing_input","observation_coverage":"unknown"}
                elif key in counts:
                    status="partial_period" if product=="viirs-snpp" and month=="2012-01" else "observed_detections_recorded"
                    row={**common,"count_raw":counts[key],"count_type0_candidate":type0[key],"harmonized_value":None,"status":status,"observation_coverage":"unknown"}
                else:
                    status="partial_period" if product=="viirs-snpp" and month=="2012-01" else "no_detections_recorded"
                    row={**common,"count_raw":0,"count_type0_candidate":0,"harmonized_value":None,"status":status,"observation_coverage":"unknown"}
                rows.append(row)
    if sum((r["count_raw"] or 0) for r in rows)!=sum(counts.values()): raise ValueError("monthly raw counts do not reconcile with normalized input rows")
    if sum((r["count_type0_candidate"] or 0) for r in rows)!=sum(type0.values()): raise ValueError("monthly type 0 counts do not reconcile with normalized input rows")
    out_manifest={"schema_version":1,"artifact_kind":"firepulse-monthly","aggregator":"pipeline.aggregate_monthly","aggregator_sha256":hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest(),"normalized_manifest_sha256":hashlib.sha256((src/"manifest.json").read_bytes()).hexdigest(),"inputs":[{"file":n,"sha256":hashes[n]} for n in sorted(hashes)],"input_files":len(entries),"source_rows":sum(counts.values()),"source_type0_rows":sum(type0.values()),"monthly_rows":len(rows),"scope":"GA country-file; geometry unverified","observation_coverage":"unknown for all rows"}
    dst.parent.mkdir(parents=True,exist_ok=True); tmp=Path(tempfile.mkdtemp(prefix=dst.name+".tmp.",dir=dst.parent))
    try:
        with (tmp/"monthly_counts.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\n"); w.writeheader();w.writerows(rows)
        (tmp/"calendar.json").write_text(json.dumps({"schema_version":1,"artifact_kind":"firepulse-monthly-calendar","start":"2000-11","end":"2025-12","sources":SATS,"source_starts":{k:v.isoformat() for k,v in STARTS.items()},"rows":rows},indent=2,sort_keys=True)+"\n",encoding="utf-8")
        out_manifest["monthly_csv_sha256"]=hashlib.sha256((tmp/"monthly_counts.csv").read_bytes()).hexdigest()
        out_manifest["calendar_sha256"]=hashlib.sha256((tmp/"calendar.json").read_bytes()).hexdigest()
        (tmp/"manifest.json").write_text(json.dumps(out_manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        if dst.exists():
            try: old=json.loads((dst/"manifest.json").read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError) as exc: raise ValueError("refusing to replace unrecognized output directory") from exc
            if old.get("artifact_kind")!="firepulse-monthly" or old.get("schema_version")!=1: raise ValueError("refusing to replace unrecognized output directory")
            backup=dst.with_name(dst.name+".previous")
            if backup.exists(): raise ValueError(f"refusing to replace output while backup exists: {backup}")
            os.replace(dst,backup)
            try: os.replace(tmp,dst)
            except Exception: os.replace(backup,dst); raise
            import shutil; shutil.rmtree(backup)
        else: os.replace(tmp,dst)
    finally:
        if tmp.exists():
            import shutil; shutil.rmtree(tmp)
    return {"input_files":len(entries),"source_rows":sum(counts.values()),"monthly_rows":len(rows)}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args(argv);aggregate(a.input,a.output);return 0
if __name__=="__main__":raise SystemExit(main())
