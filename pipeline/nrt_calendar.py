"""Build a partial 2026 NRT calendar from prepared individual observations."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def build(path: Path) -> dict:
    raw = path.read_bytes(); data = json.loads(raw)
    if data.get("artifact_kind") != "firepulse-nrt-observations" or data.get("schema_version") != 1:
        raise ValueError("unrecognized NRT observation artifact")
    observations = data.get("observations")
    if not isinstance(observations,list) or not observations or len(observations) != data.get("observation_count"):
        raise ValueError("NRT observation count mismatch")
    grouped = {}; seen_lines = set()
    for item in observations:
        stamp = item.get("acquired_at", "")
        try:
            parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
            if parsed.year != 2026: raise ValueError("wrong year")
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid 2026 UTC timestamp") from exc
        month, day = stamp[:7], stamp[:10]
        if not 1 <= int(month[5:7]) <= 12: raise ValueError("invalid month")
        line = item.get("source_line")
        if not isinstance(line,int) or isinstance(line,bool) or line < 2: raise ValueError("invalid source line")
        if line in seen_lines: raise ValueError("duplicate source line")
        seen_lines.add(line)
        bucket = grouped.setdefault(month,{"types":Counter(),"days":set()})
        kind = item.get("type_nasa")
        if kind not in (None,0,1,2,3): raise ValueError("invalid NASA type")
        bucket["types"]["unavailable" if kind is None else str(kind)] += 1
        bucket["days"].add(day)
    rows=[]
    for m in range(1,13):
        month=f"2026-{m:02d}"; bucket=grouped.get(month)
        rows.append({"month":month,"detection_count":sum(bucket["types"].values()) if bucket else None,
                     "type_counts":dict(sorted(bucket["types"].items())) if bucket else None,
                     "days_with_detections":sorted(bucket["days"]) if bucket else [],
                     "status":"partial_nrt_extract" if bucket else "not_in_extract",
                     "observation_coverage":"unknown"})
    return {"artifact_kind":"firepulse-nrt-calendar","schema_version":1,
            "observation_artifact_sha256":hashlib.sha256(raw).hexdigest(),
            "source_product_declared":data.get("source_product_declared"),
            "source_product_verified":data.get("source_product_verified",False),
            "source_file_sha256":data.get("source_sha256"),"rows":rows,
            "limitations":["Single extract; no claim of complete days or months.","Missing months are unavailable, not zero.","No deduplication, harmonization, geographic validation or database import."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=build(a.input)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(f"Prepared {len(result['rows'])} monthly statuses; coverage remains unknown")


if __name__ == "__main__": main()
