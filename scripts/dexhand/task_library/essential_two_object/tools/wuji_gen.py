"""wuji_gen.py - produce the Wuji Hand 2.2 trajectory for essential_two_object (privileged mode).

Two phases, both deterministic (fixed NumPy seeds, deterministic MuJoCo), only legal Wuji finger position targets
(the six wrist targets stay at the locked pose; walnut B's ring/pinky targets stay at their reset values):
  1. Stages 1-2 (rotate walnut A +90 deg about palm Y, return it): physics-shooting CEM/MPC. Forecasts run on a
     separate MjData copy of the task's own model; each control row is the best sampled thumb/index/middle target
     change (40 samples x 2 CEM generations, 100-substep horizon), executed in the task's Session, whose checker
     decides the stages. Runs from the reset until the checker reports stage index 2 (76 rows; stage 1 completes at row 44).
  2. Release of A into the tray while B stays held: a two-via-point thumb/index/middle opening (ramp, ramp, hold),
     whose two goal vectors (thumb/index/middle targets, exact floats) and ramp lengths were found by an authoring CEM scored with Session.step (authoring script release.py, not kept, on the stage-2 state, seed 31).
No object state, force, weld or predicate is ever written.
Usage: python wuji_gen.py [--tools <task>/environment] [--out <file>]   (~4 min on one CPU core; rewrites
../solution/wuji/trajectory.npz byte for byte; uses the Wuji start of ../wuji_reset.json as packaged)
"""
import os, sys, argparse, copy
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1"); os.environ.setdefault("OMP_NUM_THREADS", "1")
ap = argparse.ArgumentParser()
ap.add_argument("--tools", default=os.environ.get("RCB_TOOLS", "/opt/tools"))
ap.add_argument("--out", default="/app/output/trajectory.npz")
args = ap.parse_args()
sys.path.insert(0, args.tools)
import numpy as np, mujoco
from rcb_dexhand import Session

MPC = dict(samples=40, horizon=100, sigma=0.045, maxdelta=0.12, seed=2, wpos=5.0, wspeed=0.03)
RELEASE = dict(r1=2, r2=22,
    g1=[0.22440785755963213, -0.5392826202968106, 1.132849815068045, -1.047, -0.6939957584852451, -0.698, -0.3633367160884843, 1.57, 0.7707101907575667, -0.22429477647561236, 2.094, 0.45612947563347994],
    g2=[-1.187, -1.1675662909088032, 0.4224629611397329, -1.0335472274116033, -1.047, 0.698, -1.047, 0.07147625792558987, -0.15898794327045887, -0.46253423022813794, 0.6003446146611289, 1.2707131875629951])
MAXROWS = 320

s = Session("essential_two_object", hand="wuji"); m, d = s.model, s.data
forecast = mujoco.MjData(m)
shadow = copy.copy(s); shadow.data = forecast
flags = mujoco.mjtState.mjSTATE_INTEGRATION
state = np.empty(mujoco.mj_stateSize(m, flags))
active = np.arange(6, 18)
lo, hi = m.actuator_ctrlrange.T
rng = np.random.default_rng(MPC["seed"])
palm_id = m.body("right_hand_C_MC").id
in_hand = np.zeros(m.nbody, bool)
for b in range(m.nbody):
    x = b
    while x > 0 and x != palm_id:
        x = int(m.body_parentid[x])
    in_hand[b] = x == palm_id
GA, GB = m.geom("task_ball_a").id, m.geom("task_ball_b").id
wrench = np.zeros(6)


def fast_contacts(D):
    ah = bh = asup = bsup = pair = 0
    for i in range(D.ncon):
        c = D.contact[i]; g1, g2 = int(c.geom1), int(c.geom2)
        if g1 not in (GA, GB) and g2 not in (GA, GB):
            continue
        if {g1, g2} == {GA, GB}:
            pair += 1; continue
        obj, other = (g1, g2) if g1 in (GA, GB) else (g2, g1)
        mujoco.mj_contactForce(m, D, i, wrench)
        fn = float(np.linalg.norm(wrench[:3]))
        ob = int(m.geom_bodyid[other])
        if in_hand[ob]:
            if fn > 0.005:
                if obj == GA: ah += 1
                else: bh += 1
        elif ob == 0 and fn > 0.005:
            if obj == GA: asup += 1
            else: bsup += 1
    return ah, bh, asup, bsup, pair


def score(control, stage):
    H = MPC["horizon"]
    mujoco.mj_setState(m, forecast, state, flags)
    forecast.ctrl[:] = control
    max_speed = 0.0
    for k in range(H):
        mujoco.mj_step(m, forecast)
        speed = float(np.max(np.abs(forecast.qvel[s._task_dofs])))
        max_speed = max(max_speed, speed)
        if stage < 2 and speed > 11.0:
            return 1e3 + speed
        ah, bh, asup, bsup, pair = fast_contacts(forecast)
        if bh < 1 or bsup or pair or (stage < 2 and (ah < 1 or asup)):
            return 1e3 + (H - k)
        if k % 5 == 4 or k == H - 1:
            f = shadow.features()
            if f["force"] > 78 or f["ball_pair_contacts"] > 0 or f["b_support"] > 0:
                return 1e3 + (H - k)
            if f["b_position_error"] > 0.0135 or f["b_orientation_error"] > 0.18 or f["b_finger_contacts"] < 1 \
                    or f["b_hand_contacts"] < 1 or f["b_finger_contacts"] > 5:
                return 1e3 + (H - k)
            if f["a_height"] < 0.137 or f["a_deposit_distance"] > 0.098 or f["a_linear_speed"] > 2.4 or f["a_angular_speed"] > 78:
                return 1e3 + (H - k)
            if stage < 2 and (f["a_support"] > 0 or f["a_hand_contacts"] < 1 or f["a_position_error"] > 0.033):
                return 1e3 + (H - k)
    f = shadow.features()
    error = f["a_quarter_turn_error"] if stage == 0 else f["a_orientation_error"]
    return (error + MPC["wpos"] * f["a_position_error"] + 12 * f["b_position_error"] + 0.4 * f["b_orientation_error"]
            + MPC["wspeed"] * max_speed + 0.25 * f["speed"] + 0.04 * max(0, 1 - f["a_finger_contacts"]))


actions = []
last = s.hold_action(); best_delta = np.zeros(len(active))
for iteration in range(400):
    st = s.status()
    if st["done"] or s.checker.stage_index >= 2:
        break
    stage = s.checker.stage_index
    check = s.checker.stages[stage]
    bounds = {k: v for k, v in check["bounds"].items() if k != "speed"}
    if s.checker._matches(s.features(), bounds):
        s.step(last); actions.append(last.copy())
        continue
    mujoco.mj_getState(m, d, state, flags)
    base = last.copy(); mean = best_delta * 0.65; sigma = np.full(len(active), MPC["sigma"])
    best = base.copy(); best_score = score(best, stage)
    for _ in range(2):
        deltas = rng.normal(mean, sigma, size=(MPC["samples"], len(active))); deltas[0] = 0; deltas[1] = mean
        cands = []
        for delta in deltas:
            control = base.copy()
            control[active] = np.clip(base[active] + np.clip(delta, -MPC["maxdelta"], MPC["maxdelta"]), lo[active], hi[active])
            v = score(control, stage); cands.append((v, control, delta))
            if v < best_score:
                best, best_score = control, v
        cands.sort(key=lambda x: x[0]); el = cands[: max(4, MPC["samples"] // 6)]
        mean = np.mean([e[2] for e in el], 0); sigma = np.maximum(np.std([e[2] for e in el], 0), 0.012)
    best_delta = best[active] - base[active]; last = best
    s.step(best); actions.append(best.copy())
assert s.checker.stage_index == 2 and not s.status()["done"], s.status()

# Phase 2: release A, keep B.
base = actions[-1].copy(); J = np.arange(6, 18)
g1 = base.copy(); g1[J] = RELEASE["g1"]
g2 = base.copy(); g2[J] = RELEASE["g2"]
r1, r2 = RELEASE["r1"], RELEASE["r2"]
rows = [base + min(1, (i + 1) / r1) * (g1 - base) for i in range(r1)]
rows += [g1 + min(1, (i + 1) / r2) * (g2 - g1) for i in range(r2)]
rows += [g2] * (MAXROWS - len(rows))
for r in rows:
    st = s.step(r); actions.append(np.asarray(r, float).copy())
    if st["done"]:
        break
st = s.status()
print({k: st[k] for k in ("success", "stage", "steps", "reason", "state_sha")})
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
s.save_trajectory(np.asarray(actions), args.out)
