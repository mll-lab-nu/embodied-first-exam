#!/usr/bin/env python3
"""Start and end states of the frozen instances through RCB's own Session, built every way the service and its
finalize build them (needs the simulator: run it in the eai-robosafe image of the release, after make_rt_instances.py
and before gen_realtime.py render).

    python scripts/robosafe/check_double_build_rt.py [--only <slug>-iNN,...] [--modes paused,realtime] [--jobs 8]

For every task of the realtime set (make_rt_instances.py REALTIME_FAMILIES), paused (the standard instance, rcb_rsb.Session with
the standard codec) and realtime (instances_rt/, rcb_rsb_rt's codec and Episode.tick), each in a process of its own:
  - two Sessions built one after the other, a second Session built while a first is still alive, and a fresh-process
    replay: every start hash must equal the frozen instance's state_sha;
  - the reference (oracles/<task>.json rows, one journal row per control step) played on a Session built alone, on the
    second Session with the first alive, and replayed in a fresh process (rcb_rsb.replay, as the finalize's replay.py):
    the three end hashes must be equal.
Every run writes its rows to a temporary directory of its own. Exit 1 on any difference.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_rt_instances as M  # noqa: E402  (puts the assembled environment/sim/ on sys.path)


def items_of(name: str):
    import numpy as np
    orc = json.loads((HERE / "oracles" / f"{name}.json").read_text())
    npz = HERE / "oracles" / f"{name}.npz"
    arrays = dict(np.load(npz)) if npz.exists() else {}
    out = []
    for it in orc["plan"]:
        if "rows" in it:
            out += [(it["type"], arrays[it["type"]][k], "") for k in range(*it["rows"])]
        else:
            out.append((it["type"], np.asarray(it["row"], np.float64), it.get("text") or ""))
    return out


def instance(mode: str, name: str) -> dict:
    return json.loads((HERE / ("instances_rt" if mode == "realtime" else "instances") / f"{name}.json").read_text())


def one(mode: str, name: str) -> dict:
    """In this process: the builds and plays above (the caller runs it in a fresh process)."""
    import numpy as np
    if mode == "realtime":
        import rcb_rsb_rt  # noqa: F401
    import rcb_rsb
    inst, items = instance(mode, name), items_of(name)

    def play(s):
        rows = []
        for typ, row, text in items:
            note = s.notes.add(text) if text else rcb_rsb.NOTE_NONE
            raw = s.codec.encode(typ, row, note)
            rows.append(raw)
            s.step_raw(raw)
            if s.ended:
                break
        return np.asarray(rows)

    res = {"mode": mode, "task": name, "frozen": inst["state_sha"]}
    a = rcb_rsb.Session(inst)
    res["start_first"] = a.ep.state_hash()
    del a
    b = rcb_rsb.Session(inst)
    res["start_second"] = b.ep.state_hash()
    rows = play(b)
    res["final_alone"], notes = b.state_sha(), list(b.notes.texts)
    del b
    first = rcb_rsb.Session(inst)                    # a first Session alive, idle, while the second one runs
    c = rcb_rsb.Session(inst)
    res["start_beside_live"] = c.ep.state_hash()
    play(c)
    res["final_beside_live"] = c.state_sha()
    del c, first
    work = tempfile.mkdtemp(prefix="dbl_")
    try:
        np.save(os.path.join(work, "rows.npy"), rows)
        with open(os.path.join(work, "notes.json"), "w") as f:
            json.dump(notes, f)
        out = subprocess.run([sys.executable, __file__, "--replay", mode, name, os.path.join(work, "rows.npy"),
                              os.path.join(work, "notes.json")], capture_output=True, text=True, check=True)
        rep = json.loads(out.stdout.splitlines()[-1])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res["start_fresh"], res["final_fresh"] = rep["start_sha"], rep["state_sha"]
    starts = [res[k] for k in ("start_first", "start_second", "start_beside_live", "start_fresh")]
    finals = [res[k] for k in ("final_alone", "final_beside_live", "final_fresh")]
    res["ok"] = all(s == res["frozen"] for s in starts) and len(set(finals)) == 1
    return res


def main() -> int:
    if sys.argv[1:2] == ["--one"]:
        print(json.dumps(one(sys.argv[2], sys.argv[3])))
        return 0
    if sys.argv[1:2] == ["--replay"]:
        import numpy as np
        mode, name, rows, notes = sys.argv[2:6]
        if mode == "realtime":
            import rcb_rsb_rt  # noqa: F401
        import rcb_rsb
        out = rcb_rsb.replay(instance(mode, name), np.load(rows), json.loads(pathlib.Path(notes).read_text()))
        print(json.dumps({"start_sha": out["start_sha"], "state_sha": out["state_sha"]}))
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="")
    ap.add_argument("--modes", default="paused,realtime")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())["families"]
    names = [x for x in a.only.split(",") if x] or [p.stem for s in M.realtime_slugs(fams)
                                                     for p in sorted((HERE / "instances_rt").glob(f"{s}-i*.json"))]
    runs = [(m, n) for n in names for m in a.modes.split(",")]

    def run(r):
        p = subprocess.run([sys.executable, __file__, "--one", *r], capture_output=True, text=True)
        try:
            return json.loads(p.stdout.splitlines()[-1])
        except (IndexError, ValueError):
            return {"mode": r[0], "task": r[1], "ok": False, "error": p.stderr[-400:]}

    bad = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(run, runs):
            bad += not res["ok"]
            if "error" in res:
                print(f"FAIL {res['task']} {res['mode']}: {res['error']}")
                continue
            print(f"{'ok  ' if res['ok'] else 'FAIL'} {res['task']} {res['mode']:8s} start {res['frozen'][:12]} "
                  f"(first {res['start_first'][:8]}, second {res['start_second'][:8]}, beside a live one "
                  f"{res['start_beside_live'][:8]}, fresh {res['start_fresh'][:8]}) final alone {res['final_alone'][:12]}, "
                  f"beside a live one {res['final_beside_live'][:12]}, fresh replay {res['final_fresh'][:12]}", flush=True)
    print(f"{len(runs) - bad} of {len(runs)} equal")
    shutil.rmtree(os.environ["MAKE_RT_SIM"], ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
