"""Authoring negatives derived from the oracle rows: nop, truncation before the last stage, a mid-flip drop and a
knock-off push. Writes one trajectory per case next to --outdir; graders' replay.py verdicts are recorded separately."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from replay import load_trajectory  # noqa: E402
from runtime import Session  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--oracle", required=True)
ap.add_argument("--outdir", required=True)
a = ap.parse_args()
out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
rows, hand, _ = load_trajectory(a.oracle)
s = Session(hand=hand)
stages = []
s.reset()
for i, r in enumerate(rows):
    s.step(r)
    if not stages or s.checker.stage != stages[-1][1]:
        stages.append((s.steps, int(s.checker.stage)))
    if s.done:
        break
standing_step = next(st for st, g in stages if g == 2)
cases = {}
cases["nop"] = np.tile(s.initial_targets, (600, 1))
cases["truncated_before_standing"] = rows[: standing_step - 60]
cases["truncated_before_hold_end"] = rows[: stages[-1][0] - 5]
# drop: follow the oracle until the rack is held high, then open the hand and pull it away
s.reset(); hi = None
for i, r in enumerate(rows):
    s.step(r)
    if s.status()["tilt_deg"] < 100 and s.status()["hand_rack_contacts"] > 0 and hi is None:
        hi = i
        break
drop = list(rows[: hi + 1])
last = rows[hi].copy()
open_row = last.copy(); open_row[6:] = s.initial_targets[6:]
for t in range(1, 11):
    drop.append(last + (open_row - last) * t / 10)
away = open_row.copy(); away[0] -= 0.25; away[2] += 0.10
for t in range(1, 41):
    drop.append(open_row + (away - open_row) * t / 40)
drop += [away] * 300
cases["drop_mid_flip"] = np.array(drop)
# knock-off: after the unfold+legs (stage 1 reached), sweep the open hand across the rack toward the near edge (-y)
st1 = next(st for st, g in stages if g == 1)
knock = list(rows[: st1 + 20])
k0 = knock[-1].copy(); k0[6:] = s.initial_targets[6:]
p0 = k0.copy(); p0[:6] = [-0.37, 0.50, 0.20, 0.0, 1.3, 0.0]   # fingers pointing down, beyond the rack's +y edge
lo, hi_ = s.model.actuator_ctrlrange.T
p0 = np.clip(p0, lo, hi_)
ph = p0.copy(); ph[2] = 0.40
for t in range(1, 61):
    knock.append(k0 + (ph - k0) * t / 60)
for t in range(1, 41):
    knock.append(ph + (p0 - ph) * t / 40)
p1 = p0.copy(); p1[1] = -0.6
for t in range(1, 151):
    knock.append(p0 + (p1 - p0) * t / 150)
knock += [p1] * 100
cases["knock_off_push"] = np.array(knock)
info = {"stages": stages}
for name, r in cases.items():
    r = np.clip(np.asarray(r, float), lo, hi_)
    s.save_trajectory(r, out / f"{name}.npz")
    info[name] = len(r)
print(json.dumps(info))
