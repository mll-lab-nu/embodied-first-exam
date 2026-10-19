#!/usr/bin/env python3
"""Field-by-field agreement of a set of re-reviews with the current reviews (model QA for batch reviews).

usage: python3 tools/agreement.py <dir with <key>.<depth>.json re-reviews> [<dir> …]
Each dir holds re-reviews of trials that already have a current review (e.g. an Opus 10% re-check of a Sonnet batch,
or the 10-16 model pilot in /data/pingyue/cross-bench/pilot/{opus,sonnet,haiku}). Prints agreement counts per field;
cause and stage are counted on failures only. Read the disagreements on `primary` by hand: a code that contradicts the
record's own `decisive.what` is an error, a different but defensible root cause is not.
"""
from __future__ import annotations
import glob, json, os, sys
from common import HERE

CB = json.load(open(os.path.join(HERE, "meta/codebook.json")))
GROUP = {c: g for g, cs in CB["cause"].items() for c in cs}
FAIL_ONLY = {"primary", "primary_group", "stage"}


def fields(r: dict, loop) -> dict:
    f, t, s = r.get("failure") or {}, r.get("time") or {}, r.get("style") or {}
    p = f.get("primary") or ""
    return {"outcome": r.get("outcome"), "primary": p, "primary_group": GROUP.get(p, "other" if p else ""),
            "stage": f.get("stage"), "claim": r.get("claim"), "clock_aware": t.get("clock_aware"),
            "planned_budget": t.get("planned_budget"), "on_failure": s.get("on_failure"), "plan_vs_act": s.get("plan_vs_act"),
            "verification": s.get("verification"), "loop": loop}


def base(key: str, depth: str):
    p = os.path.join(HERE, "reviews", f"{key}.{depth}.json")
    if not os.path.exists(p):
        return None
    a = os.path.join(HERE, "annot/approach", key + ".json")
    return fields(json.load(open(p)), json.load(open(a)).get("loop") if os.path.exists(a) else None)


def main() -> int:
    res = {}
    for d in sys.argv[1:]:
        counts = {}
        for p in glob.glob(os.path.join(d, "*.json")):
            key, depth = os.path.basename(p).rsplit(".", 2)[:2]
            b = base(key, depth)
            if not b:
                continue
            r = json.load(open(p))
            side = os.path.join(d, "approach", key + ".json")              # QA runs write the approach label beside the record
            loop = r.get("approach_loop") or (json.load(open(side)).get("loop") if os.path.exists(side) else None)
            got = fields(r, loop)
            for k in b:
                if k in FAIL_ONLY and b["outcome"] != "failure":
                    continue
                ok, n = counts.get(k, (0, 0))
                counts[k] = (ok + (b[k] == got[k]), n + 1)
        res[os.path.basename(d.rstrip("/"))] = counts
    names = list(res)
    print("| field | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
    for k in fields({}, None):
        print(f"| {k} | " + " | ".join(f"{res[m].get(k, (0, 0))[0]}/{res[m].get(k, (0, 0))[1]}" for m in names) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
