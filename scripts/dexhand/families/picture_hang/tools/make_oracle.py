"""Authoring-only: run the closed-loop controller for one hand and save its rows (+ hold slack) as a trajectory.

python tools/make_oracle.py --hand sharpa --out solution/trajectory.npz [--slack 200]
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import numpy as np  # noqa: E402

import controller as C  # noqa: E402
from runtime import Session  # noqa: E402

PARAMS = {"sharpa": {}, "wuji": {}}  # controller defaults (x0 = -0.03 m, tucked thumb fe = 0.5) for both hands

ap = argparse.ArgumentParser()
ap.add_argument("--hand", default="sharpa")
ap.add_argument("--out", required=True)
ap.add_argument("--slack", type=int, default=200)
ap.add_argument("--params", default=None)
args = ap.parse_args()
s = Session(hand=args.hand)
c = C.Controller(s, json.loads(args.params) if args.params else PARAMS[args.hand])
status = c.run()
if not status["success"]:
    raise SystemExit(f"controller did not succeed: {status['reason']} at {status['steps']}")
rows = np.array(c.rows)
rows = np.concatenate([rows, np.repeat(rows[-1:], args.slack, 0)])  # hold rows after success (episode ends anyway)
s.save_trajectory(rows, args.out)
print(json.dumps({"hand": args.hand, "success_step": status["steps"], "rows": len(rows),
                  "sha256": hashlib.sha256(Path(args.out).read_bytes()).hexdigest()}))
