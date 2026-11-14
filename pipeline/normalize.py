"""Normalize local FIRMS CSV files without altering the source observations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PRODUCT = re.compile(r"^(modis|viirs-snpp|viirs-jpss1)_(\d{4})_Gabon\.csv$", re.I)
OUT_FIELDS = ["source", "satellite", "instrument_original", "satellite_original", "acquired_at", "latitude", "longitude", "brightness_mir", "brightness_tir", "scan", "track", "frp", "confidence_raw", "confidence_tier", "hotspot_type", "daynight", "version", "is_nrt", "source_file", "source_line", "source_sha256", "observation_hash"]

def _num(value, name, low=None, high=None):
    if value is None or not value.strip(): return ""
    try: n = float(value)
    except ValueError as exc: raise ValueError(f"invalid {name}: {value!r}") from exc
    if not math.isfinite(n) or (low is not None and n < low) or (high is not None and n > high): raise ValueError(f"out-of-domain {name}: {value!r}")
    return format(n, ".15g")

def normalize_row(row, product, rel, line, source_sha):
    required = ("latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "version", "type", "daynight")
    for field in required:
        if not (row.get(field) or "").strip(): raise ValueError(f"missing required value {field}")
    if (row["type"].strip() not in {"0", "1", "2", "3"}): raise ValueError(f"invalid type: {row['type']!r}")
    if row["daynight"].strip().lower() not in {"d", "n"}: raise ValueError(f"invalid daynight: {row['daynight']!r}")
    sat=row["satellite"].strip().lower(); instr=row["instrument"].strip().lower()
    allowed={"modis": ({"terra","aqua"},{"modis"}), "viirs-snpp": ({"suomi-npp","snpp","n"},{"viirs"}), "viirs-jpss1": ({"noaa-20","noaa20","n20","jpss-1","jpss1"},{"viirs"})}
    if sat not in allowed[product][0] or instr not in allowed[product][1]: raise ValueError(f"instrument/satellite incompatible with {product}: {row['instrument']!r}/{row['satellite']!r}")
    date = datetime.strptime((row.get("acq_date") or "").strip(), "%Y-%m-%d").date()
    if not (date.year>2000 or (date.year==2000 and date.month>=11)) or date.year>2025: raise ValueError(f"date outside M1 horizon: {date.isoformat()}")
    match=PRODUCT.fullmatch(Path(rel).name)
    if not match or date.year != int(match.group(2)): raise ValueError(f"date year does not match source filename: {rel}")
    t = (row.get("acq_time") or "").strip()
    if not t.isdigit() or len(t) > 4 or int(t) > 2359 or int(t) % 100 > 59: raise ValueError(f"invalid acq_time: {t!r}")
    hour, minute = divmod(int(t), 100)
    acquired = datetime(date.year, date.month, date.day, hour, minute, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    lat = _num(row.get("latitude"), "latitude", -90, 90); lon = _num(row.get("longitude"), "longitude", -180, 180)
    v = (row.get("version") or "").strip()
    confidence = (row.get("confidence") or "").strip()
    tier = ""
    if confidence:
        if product == "modis":
            c = _num(confidence, "confidence", 0, 100)
            tier = "low" if float(c) < 30 else "nominal" if float(c) < 80 else "high"
        elif confidence.lower() in {"l", "n", "h"}: tier = {"l":"low", "n":"nominal", "h":"high"}[confidence.lower()]
        else: raise ValueError(f"invalid confidence category: {confidence!r}")
    mir, tir = (("brightness", "bright_t31") if product == "modis" else ("bright_ti4", "bright_ti5"))
    canonical_sat={"modis":"Terra" if sat=="terra" else "Aqua", "viirs-snpp":"N", "viirs-jpss1":"N20"}[product]
    out = {"source": "viirs-noaa20" if product == "viirs-jpss1" else product, "satellite":canonical_sat, "instrument_original": (row.get("instrument") or "").strip(), "satellite_original": (row.get("satellite") or "").strip(), "acquired_at": acquired, "latitude": lat, "longitude": lon, "brightness_mir": _num(row.get(mir), mir), "brightness_tir": _num(row.get(tir), tir), "scan": _num(row.get("scan"), "scan"), "track": _num(row.get("track"), "track"), "frp": _num(row.get("frp"), "frp"), "confidence_raw": confidence, "confidence_tier": tier, "hotspot_type": row["type"].strip(), "daynight": row["daynight"].strip().upper(), "version": v, "is_nrt": str("nrt" in v.lower()).lower(), "source_file": rel, "source_sha256": source_sha}
    useful = {k: (row.get(k) or "").strip() for k in sorted(row) if k and k != "__extra__"}
    out["observation_hash"] = hashlib.sha256(json.dumps({"source":out["source"],"product":product,"fields":useful}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    out["source_line"] = str(line)
    return out

def normalize(input_dir: Path, output_dir: Path):
    src, dst = input_dir.resolve(), output_dir.resolve()
    if not src.is_dir() or src == dst or src in dst.parents or dst in src.parents: raise ValueError("invalid input/output directories; output cannot overlap input")
    all_csv=sorted((p for p in src.rglob("*.csv") if p.is_file()),key=lambda p:p.relative_to(src).as_posix())
    invalid=[p.relative_to(src).as_posix() for p in all_csv if not PRODUCT.fullmatch(p.name)]
    if invalid: raise ValueError(f"unrecognized CSV input files: {invalid}")
    files=all_csv
    if not files: raise ValueError("no recognized source CSV files")
    output_names=[p.name.replace(".csv","_normalized.csv") for p in files]
    if len(output_names)!=len(set(output_names)): raise ValueError("source basenames collide; refusing ambiguous normalized outputs")
    prepared=[]; total=Counter()
    for path in files:
        rel=path.relative_to(src).as_posix(); product=PRODUCT.fullmatch(path.name).group(1).lower(); digest=hashlib.sha256(path.read_bytes()).hexdigest(); rows=[]; seen=set(); duplicates=0
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader=csv.DictReader(f, restkey="__extra__")
            needed={"latitude","longitude","acq_date","acq_time","satellite","instrument","confidence","version","type","daynight","scan","track","frp"} | ({"brightness","bright_t31"} if product=="modis" else {"bright_ti4","bright_ti5"})
            if not reader.fieldnames or needed-set(reader.fieldnames): raise ValueError(f"{rel}: missing columns {sorted(needed-set(reader.fieldnames or []))}")
            for line,row in enumerate(reader,2):
                if row.get("__extra__") or any(v is None for k,v in row.items() if k != "__extra__"): raise ValueError(f"{rel}:{line}: malformed CSV row")
                out=normalize_row(row,product,rel,line,digest); sig=out["observation_hash"]
                duplicates += sig in seen; seen.add(sig); rows.append(out)
        total.update(rows=len(rows), duplicate_exact_rows=duplicates); prepared.append((path.name,rows,digest,duplicates))
    dst.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix=dst.name+".tmp.",dir=dst.parent))
    try:
        manifests=[]
        for name,rows,digest,dups in prepared:
            outname=name.replace(".csv","_normalized.csv"); p=temp/outname
            with p.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=OUT_FIELDS,lineterminator="\n"); w.writeheader(); w.writerows(rows)
            mm=PRODUCT.fullmatch(name); manifests.append({"source_file":name,"product":"viirs-noaa20" if mm.group(1).lower()=="viirs-jpss1" else mm.group(1).lower(),"year":int(mm.group(2)),"source_sha256":digest,"output_file":outname,"input_rows":len(rows),"output_rows":len(rows),"duplicate_exact_rows":dups,"output_sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
        code_hash=hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()
        (temp/"manifest.json").write_text(json.dumps({"schema_version":1,"artifact_kind":"firepulse-normalized","normalizer":"pipeline.normalize","normalizer_sha256":code_hash,"files":manifests,"input_rows":total["rows"],"output_rows":total["rows"],"duplicate_exact_rows":total["duplicate_exact_rows"]},indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
        if dst.exists():
            try: old=json.loads((dst/"manifest.json").read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError) as exc: raise ValueError("refusing to replace unrecognized output directory") from exc
            if old.get("artifact_kind")!="firepulse-normalized" or old.get("schema_version")!=1: raise ValueError("refusing to replace unrecognized output directory")
            backup=dst.with_name(dst.name+".previous")
            if backup.exists(): raise ValueError(f"refusing to replace output while backup exists: {backup}")
            os.replace(dst,backup)
            try: os.replace(temp,dst)
            except Exception: os.replace(backup,dst); raise
            import shutil; shutil.rmtree(backup)
        else: os.replace(temp,dst)
    finally:
        if temp.exists():
            import shutil; shutil.rmtree(temp)
    return total

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(argv); normalize(a.input,a.output); return 0
if __name__=="__main__": raise SystemExit(main())
