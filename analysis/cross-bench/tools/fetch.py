#!/usr/bin/env python3
"""Download trial files into $XB_RAW/<key>/ (default /data/pingyue/cross-bench/raw).

usage: BEL_TOKEN=... tools/fetch.py [--keys K ...] [--all] [--media] [--jobs 4]

Light set (always): trial.json (monitor record + detail), agent/trajectory.json, final.json, verifier reward/grade,
the agent's code under artifacts/app/output/, the last replay frame. --media adds the graded replay video.
--all takes every non-infra trial in $XB_DATA/trials.csv. A trial whose fingerprint changed is re-fetched; finished
downloads are kept otherwise. Requests use the current trial id (`trial_id`, either id format); the directory name is
common.trial_key, so caches from older ids are reused. The api/trial detail cached by index.py is reused when present.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys, urllib.error
from concurrent.futures import ThreadPoolExecutor
import bel
from common import RAW, read_csv
from index import cached, name

LIGHT = re.compile(r"(^agent/trajectory\.json$|/final\.json$|^verifier/(reward\.json|grade\.log)$|"
                   r"^artifacts/app/output/.+\.(py|json|txt|md)$|replay\.last\.png$)")
MEDIA = re.compile(r"(^verifier/replay\.mp4$|^artifacts/data/replay\.mp4$)")


def fetch(row: dict, media: bool) -> str:
    d = os.path.join(RAW, row["key"])
    meta = os.path.join(d, "trial.json")
    if os.path.exists(meta) and json.load(open(meta))["fingerprint"] != row["fingerprint"]:
        shutil.rmtree(d)                       # rerun replaced this trial: start clean
    os.makedirs(d, exist_ok=True)
    if os.path.exists(meta) and not media:
        return "kept"
    tid = row.get("trial_id") or row["id"]
    detail = cached(name(tid)).get("detail") or bel.get_json("api/trial", id=tid)
    want = [p for p in detail.get("files", []) if LIGHT.search(p) or (media and MEDIA.search(p))]
    missing = []
    for p in want:
        dst = os.path.join(d, p)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            body = bel.get_file(tid, p)
        except urllib.error.HTTPError as e:
            missing.append(f"{p} (HTTP {e.code})")
            continue
        open(dst + ".part", "wb").write(body)
        os.replace(dst + ".part", dst)
    json.dump({"fingerprint": row["fingerprint"], "row": row, "detail": detail, "not_served": missing},
              open(meta + ".part", "w"))
    os.replace(meta + ".part", meta)
    return f"fetched {len(want)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--media", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    rows = [r for r in read_csv("trials.csv") if (a.all and r["validity"] != "infra") or r["key"] in set(a.keys)]
    n = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for row, res in zip(rows, ex.map(lambda r: _safe(r, a.media), rows)):
            n += 1
            if not res.startswith("kept") or n % 500 == 0:
                print(f"{n}/{len(rows)} {row['key']} {res}", flush=True)
    return 0


def _safe(row: dict, media: bool) -> str:
    try:
        return fetch(row, media)
    except Exception as e:                     # one bad trial must not stop the batch; rerun picks it up
        return f"error {type(e).__name__}: {e}"


if __name__ == "__main__":
    sys.exit(main())
