#!/usr/bin/env python3
"""Replay probe: speed-limit check of the rows (from the keyframe ctrl), open-loop replay through rcb_ikea.Session
(clamp in), final_check(), wall time, optional progress log. usage: probe.py TASK REF.npz OUT.json [--every N]"""
import json, os, sys, time
sys.path.insert(0, os.environ.get("RCB_SHARED", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared")))
import numpy as np
import rcb_ikea as R

task, ref, out = sys.argv[1:4]
every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 0
env = {k: os.environ.get(k) for k in ("SW_FROM_OP", "SW_FROM_T", "NPY_DISABLE_CPU_FEATURES", "OPENBLAS_CORETYPE", "OMP_NUM_THREADS")}
t0 = time.time()
s = R.Session(task)
init = s.state_sha()
z = np.load(ref)
ctrl = R.load_trajectory(ref, s.nu, s.timestep)
k0 = s.data.ctrl.copy()
lim = s.step_limit
prev = np.vstack([k0[None], ctrl[:-1]])
d = np.abs(np.clip(ctrl, s._clo, s._chi) - prev)
fin = np.isfinite(lim)
ratio = (d[:, fin] / lim[fin])
over = (d[:, fin] > lim[fin] + R.SPEED_TOL).any(1)
spd = dict(rows=len(ctrl), rows_over=int(over.sum()), first_over=int(np.argmax(over)) if over.any() else None,
           max_ratio=float(ratio.max()), first_row_ratio=float(ratio[0].max()), clipped_by_range=int((ctrl != np.clip(ctrl, s._clo, s._chi)).any(1).sum()))
mech = getattr(s.S, "mech", None)
sw = None
if mech is not None and hasattr(mech, "sw_from"):
    sw = dict(sw_from=mech.sw_from, sw_from_t=mech.sw_from_t)
log = []
t1 = time.time()
for i, row in enumerate(ctrl):
    s.step(row)
    if every and (i + 1) % every == 0:
        log.append(dict(row=i + 1, wall=round(time.time() - t1, 1), goal=bool(s.success().get("success")), breakdown=s.validity.breakdown))
        print(json.dumps(log[-1]), flush=True)
t_run = time.time() - t1
fc = s.final_check()
res = dict(task=task, ref=ref, initial_state_sha=init, env=env, speed=spd, sw_cutover=sw, slewed_ticks=s.slewed_ticks,
           success=fc["success"], state_sha=fc["state_sha"], settled_sha=fc["settled_sha"],
           end={k: fc["end"][k] for k in ("success", "goal", "released", "at_rest", "breakdown", "terminal", "report")},
           settled={k: fc["settled"][k] for k in ("success", "goal", "released", "at_rest", "breakdown", "terminal")},
           wall_run_s=round(t_run, 1), wall_total_s=round(time.time() - t0, 1), host=os.uname().nodename, log=log)
try:
    res["cpu"] = [l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")][0]
except Exception:
    pass
json.dump(res, open(out, "w"), default=R._plain, indent=1)
print(json.dumps({k: res[k] for k in ("success", "state_sha", "settled_sha", "slewed_ticks", "wall_run_s", "speed")}, default=R._plain))
