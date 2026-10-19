#!/usr/bin/env python3
"""Snapshot of the monitor's global results (user 10-18 night: success rates come from these, not from the sample).

usage: BEL_TOKEN=… python3 tools/perf.py        (writes $XB_DATA/perf.json; the token is never written)

For each of the monitor's runs (`runs` of the first reply), GET api/model?run=<run>&source=archive and keep per row only
u (run), t (task dir), b (bench), m (mode), s (status), sc (counted), e (1 = outside the core set), v (validated),
c (configuration index), id (trial id). The monitor's rule (its `magg`): a row counts when sc == 1; graded = s in
{success, failed}; rate = success / graded. queries.load_perf reads the file; core = the task (dir without its mode
suffix) is listed in tools/data/core_set.toml (since 10-19 the monitor's e flag no longer matches the toml).
The check at the end compares the monitor's tasks with tools/data/core_set.toml.
"""
from __future__ import annotations
import json, os, re, sys, time
import bel
from common import DATA, HERE

KEEP = ("u", "t", "b", "m", "s", "sc", "e", "v", "c", "id")
OUT = os.path.join(DATA, "perf.json")


def fetch() -> dict:
    first = bel.get_json("api/model", run="codex-gpt6_luna-xhigh", source="archive")
    runs, rows = first["runs"], []
    for run in runs:
        d = first if run == first["run"] else bel.get_json("api/model", run=run, source="archive")
        rows += [{k: r.get(k) for k in KEEP} for r in d["rows"] if r.get("u") == run]
        print(f"{run}: {sum(r['u'] == run for r in rows)} rows")
    return {"time": time.strftime("%Y-%m-%d %H:%M", time.localtime()), "source": bel.BASE + "api/model?source=archive",
            "runs": runs, "rows": rows}


def check(d: dict) -> None:
    """Print how the monitor's tasks compare with tools/data/core_set.toml (one entry per task since 10-19)."""
    core = set(re.findall(r'^task = "([^"]+)"', open(os.path.join(HERE, "tools", "data", "core_set.toml")).read(), re.M))
    base = lambda r: r["t"][:-len(r["m"]) - 1] if r["t"].endswith("-" + r["m"]) else r["t"]
    seen = {base(r) for r in d["rows"]}
    print(f"core_set.toml: {len(core)} tasks; in toml without a row: {len(core - seen)} {sorted(core - seen)[:6]}; "
          f"core dirs with a row: {len({r['t'] for r in d['rows'] if base(r) in core})}")


def main() -> int:
    if not os.environ.get("BEL_TOKEN"):
        if os.path.exists(OUT):
            print(f"BEL_TOKEN not set: keeping the old snapshot {OUT} ({json.load(open(OUT))['time']})")
            return 0
        sys.exit("BEL_TOKEN not set and no snapshot yet")
    d = fetch()
    os.makedirs(DATA, exist_ok=True)
    with open(OUT + ".part", "w") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(OUT + ".part", OUT)
    print(f"{len(d['rows'])} rows from {len(d['runs'])} runs -> {OUT} ({d['time']})")
    check(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
