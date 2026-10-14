"""Regenerate the Wuji essential_pen_regrasp trajectory (authoring chain; motor targets only).

The rows were found by a sampling-based beam search over short finger-target segments (beam.py), run in five
consecutive searches, each starting from the previous search's best prefix. Every candidate is a sequence of Wuji
finger position targets (wrist rows fixed at the locked pose) executed by the task's own Session; the simulator
state is only forked/restored between candidates (mj_getState/mj_setState), never written by the policy. Physics
is deterministic, the RNG seeds come from the parent process, so the chain reproduces the rows bit for bit.

    PYTHONPATH=tasks/dexhand-essential-pen-regrasp-i00-privileged/environment \
        python wuji_gen.py --outdir <dir> --workers 3      # about 12 min; writes <dir>/trajectory.npz,
                                                           # byte-identical to ../solution/wuji/trajectory.npz
"""
import argparse, json, os, subprocess, sys
from pathlib import Path
import numpy as np

CHAIN = [  # (name, beam.py parameters); "start" is the previous stage's output
    ("s1a", {"levels": 40, "dw": 0, "keep_last": 1}),                                   # advance the pen (mode 1)
    ("s1b", {"levels": 40, "cw": 8, "seed": 2}),                                         # second fingertip contact, stage 1
    ("s2", {"mode": 2, "levels": 80, "K": 8, "M": 8, "seed": 3, "fingers": "TFMRL", "xw": 2000, "use_best": 1}),  # turn + tripod (the original run was stopped after level 79, its best)
    ("h1", {"mode": 3, "levels": 40, "K": 8, "M": 8, "L": 5, "sig": 0.03, "seed": 5, "fingers": "TFM", "use_best": 1}),  # hold
    ("h2", {"mode": 3, "levels": 30, "K": 12, "M": 12, "L": 5, "sig": 0.02, "seed": 7, "fingers": "TFM", "zero_child": 1}),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", required=True); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip", type=int, default=0, help="reuse the outputs of the first N stages already in --outdir")
    a = ap.parse_args(); out = Path(a.outdir).resolve(); out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent; prev = None   # beam.py sits next to this script
    for k, (name, params) in enumerate(CHAIN):
        if k < a.skip:
            prev = str(out / (f"{name}_best.npz" if params.get("use_best") else f"{name}.npz")); continue
        p = {k: v for k, v in params.items() if k != "use_best"}
        p.update(out=str(out / f"{name}.pkl"), workers=a.workers)
        if prev: p["start"] = prev
        subprocess.run([sys.executable, "beam.py", json.dumps(p)], cwd=here, check=True,
                       stdout=open(out / f"{name}.log", "w"), stderr=subprocess.STDOUT)
        prev = str(out / (f"{name}_best.npz" if params.get("use_best") else f"{name}.npz"))
        print(name, "->", prev, np.load(prev)["actions"].shape, flush=True)
    # the task runtime (runtime.Session) comes from PYTHONPATH, as for beam.py
    from runtime import Session
    rows = np.load(prev)["actions"].astype(np.float64)
    s = Session("essential_pen_regrasp", hand="wuji"); print(s.replay(rows))
    s.save_trajectory(rows, a.out or str(out / "trajectory.npz"))

if __name__ == "__main__":
    main()
