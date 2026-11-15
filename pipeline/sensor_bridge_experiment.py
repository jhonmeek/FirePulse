"""Exploratory NOAA-20 to S-NPP monthly ratio with chronological holdout."""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from pipeline.temporal_experiment import metrics, month_range


def experiment(calendar: Path, manifest: Path):
    raw = calendar.read_bytes()
    if hashlib.sha256(raw).hexdigest() != json.loads(manifest.read_text(encoding="utf-8"))["calendar_sha256"]:
        raise ValueError("calendar checksum mismatch")
    data = defaultdict(dict)
    for row in json.loads(raw)["rows"]:
        data[row["month"]][row["source"]] = row
    periods = {"fit": ("2018-04", "2019-12"), "diagnostic": ("2020-01", "2022-12"), "evaluate": ("2023-01", "2025-12")}
    samples, excluded = {}, {}
    for label, (start, end) in periods.items():
        samples[label], excluded[label] = [], []
        for month in month_range(start, end):
            snpp = data[month].get("viirs-snpp"); n20 = data[month].get("viirs-noaa20")
            if any(row is None or row.get("status") != "observed_detections_recorded" or row.get("count_raw") is None for row in (snpp, n20)):
                excluded[label].append(month); continue
            samples[label].append((month, n20["count_raw"], snpp["count_raw"]))
        if not samples[label]: raise ValueError(f"no eligible observations: {label}")
    total = sum(x for _, x, _ in samples["fit"])
    if not total: raise ValueError("NOAA-20 fit count is zero")
    ratio = sum(y for _, _, y in samples["fit"]) / total
    evaluations = {}
    for label in ("diagnostic", "evaluate"):
        rows = samples[label]
        evaluations[label] = metrics([ratio*x for _,x,y in rows], [y for _,x,y in rows])
    return {"artifact_kind":"firepulse-m1-bridge-experiment", "schema_version":1, "calendar_sha256":hashlib.sha256(raw).hexdigest(), "periods":periods, "eligible_months":{k:len(v) for k,v in samples.items()}, "excluded_months":excluded, "formula":"S-NPP estimated = NOAA-20 count * ratio", "ratio":ratio, "metrics":evaluations, "limitations":["Unmasked country-file detections; geometry unverified and observation coverage unknown.", "Only months with recorded detections in both products are eligible.", "2020-2025 was previously inspected; evaluation is not a blind final holdout.", "Monthly count conversion does not establish physical equivalence or validate 2026 NRT."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calendar",type=Path,default=Path("data/processed/monthly/calendar.json"))
    p.add_argument("--manifest",type=Path,default=Path("data/processed/monthly/manifest.json"))
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=experiment(a.calendar,a.manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == "__main__": main()
