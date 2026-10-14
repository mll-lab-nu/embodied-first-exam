#!/usr/bin/env python3
"""Run every family's reference controller (oracles/<family>/oracle.py) in the simulator image, check it, and record
the rows it stepped for the standard twin's reference solution (oracles/<family>/standard_rows.npz) with what it
measured (oracles/<family>/result.json: steps, time, the referee's metrics; the tasks' texts quote it):

    RFO_RW=1 scripts/roboolympics/dev.sh /rfo/make_oracles.py [--only a,b]

A controller counts when the referee says success live and a fresh replay of its sim rows succeeds and ends in the same
state. The table it prints (steps, time, margin metrics) is the families' reference-solution evidence."""
import argparse
import importlib.util
import json
import pathlib
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from rcb_rfo import Session  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())["families"]
    only = [f for f in a.only.split(",") if f]
    bad = 0
    for fam in fams:
        src = HERE / "oracles" / fam / "oracle.py"
        if (only and fam not in only) or not src.is_file():
            continue
        # a task directory holds one family: rfo.load_task finds it by name here
        spec = importlib.util.spec_from_file_location(f"oracle_{fam.replace('-', '_')}", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        t = time.time()
        s = Session(str(HERE / "instances" / f"{fam}-i00.json"))
        mod.solve(s)
        st = s.status()
        rep = s.replay()
        ok = bool(st["success"] and rep["success"] and rep["state_sha"] == st["state_sha"])
        bad += not ok
        print(json.dumps({"family": fam, "ok": ok, "live": st["success"], "replay": rep["success"],
                          "deterministic": rep["state_sha"] == st["state_sha"], "failed": st["failed"],
                          "steps": st["steps"], "time_s": st["time_s"], "metrics": st["metrics"],
                          "wall_s": round(time.time() - t, 1)}), flush=True)
        if ok and not a.no_write:
            (HERE / "oracles" / fam / "result.json").write_text(json.dumps(
                {"family": fam, "steps": st["steps"], "time_s": st["time_s"], "time_limit_s": s.instance["time_limit_s"],
                 "metrics": st["metrics"], "deterministic": True}, indent=1) + "\n")
            types = s.action_types
            names = list(types)
            dims = np.array([types[n]["dim"] for n in names], dtype=np.int64)
            rows = np.zeros((len(s.typed), int(dims.max())), dtype=np.float64)
            typ = np.zeros(len(s.typed), dtype=np.uint8)
            for i, (name, row) in enumerate(s.typed):
                typ[i] = names.index(name)
                rows[i, :len(row)] = row
            if len(s.typed) != len(s.rows):
                raise RuntimeError(f"{fam}: the controller stepped sim rows directly (s.step_raw); the standard twin "
                                   "needs typed rows (s.step)")
            np.savez_compressed(HERE / "oracles" / fam / "standard_rows.npz", names=np.array(names), dims=dims, type=typ,
                                rows=rows)
        s.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
