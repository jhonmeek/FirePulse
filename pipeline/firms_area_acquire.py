"""Download one bounded FIRMS area CSV window without logging the MAP_KEY."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PRODUCTS = {"VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP", "VIIRS_SNPP_NRT", "VIIRS_SNPP_SP", "MODIS_NRT", "MODIS_SP"}
MAX_BYTES = 10_000_000


def acquire(product: str, start: date, days: int, output_dir: Path, key: str, bbox: tuple[float,float,float,float] = (8,-4,15,3)) -> dict:
    if product not in PRODUCTS or not 1 <= days <= 5: raise ValueError("unsupported product or day range; expected 1–5 days")
    if not re.fullmatch(r"[A-Za-z0-9]{32}",key): raise ValueError("FIRMS_MAP_KEY missing or malformed")
    west,south,east,north=bbox
    if not (-180<=west<east<=180 and -90<=south<north<=90): raise ValueError("invalid bounding box")
    end=start+timedelta(days=days-1)
    name=f"{product.lower()}_{start.isoformat()}_{end.isoformat()}"
    output_dir.mkdir(parents=True,exist_ok=True)
    csv_path=output_dir/(name+".csv"); manifest_path=output_dir/(name+".manifest.json")
    if csv_path.exists() or manifest_path.exists(): raise FileExistsError("acquisition destination already exists")
    area=",".join(str(x) for x in bbox)
    url=f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{area}/{days}/{start.isoformat()}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"FirePulse-M1/1.0"}),timeout=45) as response:
            raw=response.read(MAX_BYTES+1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"FIRMS request failed: HTTP {exc.code}") from None
    except (urllib.error.URLError,OSError):
        raise RuntimeError("FIRMS request failed: network error") from None
    if len(raw)>MAX_BYTES: raise ValueError("FIRMS response exceeds size limit")
    try: text=raw.decode("utf-8-sig")
    except UnicodeDecodeError: raise ValueError("FIRMS response is not UTF-8") from None
    reader=csv.DictReader(io.StringIO(text),restkey="__extra__")
    required={"latitude","longitude","acq_date","acq_time","satellite","instrument","version"}
    if not reader.fieldnames or required-set(reader.fieldnames): raise ValueError("FIRMS response is not a supported CSV")
    count=0; dates=set()
    for row in reader:
        if row.get("__extra__") or any(v is None for k,v in row.items() if k!="__extra__"): raise ValueError("malformed FIRMS CSV row")
        try: acquired=date.fromisoformat(row["acq_date"])
        except (TypeError,ValueError): raise ValueError("invalid acquisition date") from None
        if not start<=acquired<=end: raise ValueError("FIRMS response outside requested dates")
        try:
            lat,lon=float(row["latitude"]),float(row["longitude"])
        except (ValueError,TypeError): raise ValueError("invalid coordinates") from None
        if not math.isfinite(lat) or not math.isfinite(lon) or not (south<=lat<=north and west<=lon<=east):
            raise ValueError("FIRMS response outside requested bounding box")
        time=row["acq_time"].zfill(4)
        if not re.fullmatch(r"\d{4}",time) or int(time[:2])>23 or int(time[2:])>59:
            raise ValueError("invalid acquisition time")
        dates.add(acquired.isoformat());count+=1
    manifest={"artifact_kind":"firepulse-firms-area-acquisition","schema_version":1,"source":"NASA FIRMS area API",
              "product":product,"product_verification":"requested_not_independently_verified","requested_start":start.isoformat(),"requested_end":end.isoformat(),
              "requested_bbox":list(bbox),"dataset_scope":"bounding_box_not_filtered_to_gabon",
              "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"csv_file":csv_path.name,
              "csv_sha256":hashlib.sha256(raw).hexdigest(),"rows":count,"dates_with_detections":sorted(dates),
              "type_column_present":"type" in reader.fieldnames,"observation_coverage":"unknown",
              "limitations":["Missing detections do not prove complete observation or absence of fire.","Area includes locations outside Gabon until a boundary filter is applied.","NRT products may later be replaced by standard processing."]}
    # A pre-existing destination is never overwritten; remove a newly created CSV if the manifest cannot be created.
    csv_created=False; manifest_created=False
    try:
        with csv_path.open("xb") as stream:
            csv_created=True
            stream.write(raw)
        with manifest_path.open("x",encoding="utf-8",newline="\n") as stream:
            manifest_created=True
            json.dump(manifest,stream,indent=2,sort_keys=True);stream.write("\n")
    except Exception:
        if csv_created: csv_path.unlink(missing_ok=True)
        if manifest_created: manifest_path.unlink(missing_ok=True)
        raise
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--product",required=True);p.add_argument("--start",type=date.fromisoformat,required=True)
    p.add_argument("--days",type=int,required=True);p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args()
    try: result=acquire(a.product,a.start,a.days,a.output_dir,os.environ.get("FIRMS_MAP_KEY",""))
    except (ValueError,RuntimeError,OSError) as exc:
        p.exit(1,f"Acquisition failed: {exc}\n")
    print(json.dumps(result,indent=2,sort_keys=True));return 0


if __name__=="__main__": raise SystemExit(main())
