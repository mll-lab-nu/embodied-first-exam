#!/usr/bin/env python3
"""Review records: reviews/<key>.<depth>.json, written by reviewer subagents, checked here.

usage: tools/review.py check [FILE ...]   # validate against meta/codebook.json and the trial's fingerprint
       tools/review.py table              # flatten current reviews into data/reviews.csv

A review is current while its fingerprint equals the trial's in data/trials.csv; a rerun makes it stale (kept on
disk, ignored by queries) and the trial returns to the review queue.
"""
from __future__ import annotations
import glob, json, os, sys
from common import HERE, read_csv, write_csv

REVIEWS = os.path.join(HERE, "reviews")
CODEBOOK = json.load(open(os.path.join(HERE, "meta/codebook.json")))
CAUSES = {c for group in CODEBOOK["cause"].values() for c in group}
REQUIRED = ["key", "depth", "fingerprint", "codebook", "prompt", "outcome", "headline", "approach", "story",
            "claim", "time", "style", "notable", "case_worthy"]


def load_all() -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(REVIEWS, "*.json"))):
        try:
            r = json.load(open(p))
        except ValueError:
            continue
        r["_file"] = p
        out.append(r)
    return out


def current_reviews() -> dict:
    fp = {t["key"]: t["fingerprint"] for t in read_csv("trials.csv")}
    return {(r["key"], r["depth"]): r for r in load_all() if fp.get(r.get("key")) == r.get("fingerprint")}


def problems(r: dict, fp: dict) -> list[str]:
    bad = [f"missing {k}" for k in REQUIRED if k not in r]
    if fp.get(r.get("key")) != r.get("fingerprint"):
        bad.append("fingerprint does not match trials.csv")
    for p in (r.get("approach") or {}).get("paradigm", []):
        if p not in CODEBOOK["paradigm"]:
            bad.append(f"paradigm {p}")
    f = r.get("failure")
    if r.get("outcome") == "failure":
        if not f:
            bad.append("failure block missing")
        else:
            if f.get("stage") not in CODEBOOK["stage"]:
                bad.append(f"stage {f.get('stage')}")
            for c in [f.get("primary")] + list(f.get("secondary") or []):
                if c not in CAUSES and not str(c).startswith("other:"):
                    bad.append(f"cause {c}")
    if r.get("claim") not in CODEBOOK["claim"]:
        bad.append(f"claim {r.get('claim')}")
    return bad


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    fp = {t["key"]: t["fingerprint"] for t in read_csv("trials.csv")}
    if cmd == "check":
        files = sys.argv[2:] or sorted(glob.glob(os.path.join(REVIEWS, "*.json")))
        n_bad = 0
        for p in files:
            try:
                r = json.load(open(p))
            except ValueError as e:
                print(f"{os.path.basename(p)}: invalid JSON ({e})")
                n_bad += 1
                continue
            bad = problems(r, fp)
            if bad:
                n_bad += 1
                print(f"{os.path.basename(p)}: " + "; ".join(bad))
        print(f"{len(files)} checked, {n_bad} with problems")
        return int(n_bad > 0)
    rows = []
    for (key, depth), r in sorted(current_reviews().items()):
        f = r.get("failure") or {}
        t = r.get("time") or {}
        rows.append({"key": key, "depth": depth, "outcome": r["outcome"], "headline": r["headline"],
                     "paradigm": "|".join(r["approach"].get("paradigm", [])), "stage": f.get("stage", ""),
                     "primary": f.get("primary", ""), "secondary": "|".join(f.get("secondary") or []),
                     "claim": r["claim"], "clock_aware": t.get("clock_aware", ""), "time_plan": t.get("planned_budget", ""),
                     "case_worthy": r["case_worthy"].get("score", 0) if isinstance(r["case_worthy"], dict) else r["case_worthy"],
                     "codebook": r["codebook"], "prompt": r["prompt"]})
    write_csv("reviews.csv", rows)
    print(len(rows), "current reviews")
    return 0


if __name__ == "__main__":
    sys.exit(main())
