#!/usr/bin/env python3
"""Prepare queued trials for review and print reviewer batches.

usage: BEL_TOKEN=... tools/prep.py --depth skim|deep [--batch 8] [--limit N]

Builds digests for every queued trial of that depth (deep also fetches the replay and extracts frames), then prints
batches as JSON lines: {"depth", "bench", "keys"}; trials of one benchmark share a batch so a reviewer reads its
background once.
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
import digest, fetch, media
from common import RAW, read_csv
from sample import queue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", required=True, choices=["skim", "deep"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    rows = {t["key"]: t for t in read_csv("trials.csv")}
    keys = [k for k in queue(a.depth) if k in rows][: a.limit]
    by_bench = defaultdict(list)
    for k in keys:
        if a.depth == "deep":
            try:                                  # a missing replay only costs the frames, not the review
                fetch.fetch(rows[k], media=True)
                media.frames(k)
            except Exception as e:
                print(f"{k}: media skipped ({type(e).__name__}: {e})", file=sys.stderr)
        need = "timeline.md" if a.depth == "deep" else "skeleton.md"
        if not os.path.exists(os.path.join(RAW, k, need)):
            if not os.path.exists(os.path.join(RAW, k, "trial.json")):   # the monitor did not serve this trial's files
                print(f"{k}: skipped (no fetched files)", file=sys.stderr)
                continue
            print(digest.build(k), file=sys.stderr)
        by_bench[rows[k]["bench"]].append(k)
    for bench, ks in sorted(by_bench.items()):
        for i in range(0, len(ks), a.batch):
            print(json.dumps({"depth": a.depth, "bench": bench, "keys": ks[i:i + a.batch]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
