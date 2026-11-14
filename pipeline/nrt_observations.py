"""Prepare individual 2026 NRT observations while preserving unknown NASA types."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

PRODUCTS = {"VIIRS_NOAA20_NRT": ("viirs-noaa20", {"n20", "noaa-20", "noaa20"}, "viirs"),
            "VIIRS_SNPP_NRT": ("viirs-snpp", {"n", "snpp", "suomi-npp"}, "viirs"),
            "MODIS_NRT": ("modis", {"terra", "aqua"}, "modis")}
FIELDS = ("latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "version", "daynight")


def prepare(source: Path, product: str) -> dict:
    if product not in PRODUCTS: raise ValueError("unsupported declared product")
    raw=source.read_bytes(); source_hash=hashlib.sha256(raw).hexdigest()
    expected_source, satellites, instrument=PRODUCTS[product]
    observations=[]
    with source.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream,restkey="__extra__")
        if not reader.fieldnames or set(FIELDS)-set(reader.fieldnames): raise ValueError("missing required FIRMS columns")
        for line,row in enumerate(reader,2):
            if row.get("__extra__") or any(v is None for k,v in row.items() if k!="__extra__"):
                raise ValueError(f"malformed row {line}")
            if any(not (row.get(k) or "").strip() for k in FIELDS): raise ValueError(f"missing required value at row {line}")
            lat,lon=float(row["latitude"]),float(row["longitude"])
            if not (math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180): raise ValueError(f"invalid coordinates at row {line}")
            for field in ("bright_ti4", "bright_ti5", "brightness", "bright_t31", "scan", "track", "frp"):
                if (row.get(field) or "").strip():
                    value=float(row[field])
                    if not math.isfinite(value): raise ValueError(f"invalid {field} at row {line}")
            acquired=date.fromisoformat(row["acq_date"].strip())
            if acquired.year!=2026: raise ValueError(f"outside 2026 at row {line}")
            clock=row["acq_time"].strip()
            if not clock.isdigit() or len(clock)>4 or int(clock)>2359 or int(clock)%100>59: raise ValueError(f"invalid time at row {line}")
            sat=row["satellite"].strip(); inst=row["instrument"].strip()
            if sat.lower() not in satellites or inst.lower()!=instrument: raise ValueError(f"product/satellite mismatch at row {line}")
            kind=(row.get("type") or "").strip()
            if kind and kind not in {"0","1","2","3"}: raise ValueError(f"invalid type at row {line}")
            daynight=row["daynight"].strip().upper()
            if daynight not in {"D","N"}: raise ValueError(f"invalid day/night at row {line}")
            confidence=row["confidence"].strip()
            if instrument=="viirs" and confidence.lower() not in {"l","n","h"}: raise ValueError(f"invalid confidence at row {line}")
            if instrument=="modis":
                value=float(confidence)
                if not math.isfinite(value) or not 0<=value<=100: raise ValueError(f"invalid confidence at row {line}")
            hh,mm=divmod(int(clock),100)
            stamp=datetime(acquired.year,acquired.month,acquired.day,hh,mm,tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
            # Preserve every original field, including missing optional columns and version.
            observations.append({"source":expected_source,"satellite_original":sat,"acquired_at":stamp,"latitude":lat,"longitude":lon,
                                 "type_nasa":int(kind) if kind else None,"type_status":"provided" if kind else "unavailable",
                                 "source_file":source.name,"source_sha256":source_hash,"source_line":line,"original_fields":row})
    if not observations: raise ValueError("empty input")
    return {"artifact_kind":"firepulse-nrt-observations","schema_version":1,"source_product_declared":product,
            "source_product_verified":False,"source_sha256":source_hash,"observation_count":len(observations),
            "observations":observations,"limitations":["Product and geographic provenance require independent confirmation.",
            "Missing type is unknown; no classification, deduplication, harmonization or database import.",
            "Observation coverage and missing months are unknown."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True);p.add_argument("--product",required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=prepare(a.input,a.product)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,sort_keys=True);stream.write("\n")
    print(f"Prepared {result['observation_count']} NRT observations with source provenance")


if __name__=="__main__": main()
