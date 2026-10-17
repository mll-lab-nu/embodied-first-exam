#!/usr/bin/env python3
"""Per-tick forensics of a stress episode from its checkpoint (read-only; the physics as is).
usage: forensic.py TASK CKPT_DIR ROWS.npz OUT.json [--bodies a,b,c] [--n N]
Per tick: each listed body's COM and speed; the stand's kinetic energy; the robot's contact work on the listed bodies
this tick (sum over robot-body contacts of the contact force on the body . the body's point velocity x dt); the
listed bodies' contacts with the table; the deepest part contact; rcb_ikea Validity breakdown; MuJoCo warnings."""
import json, os, pickle, sys
sys.path.insert(0, os.environ["RCB_SHARED"])
import numpy as np, mujoco
import rcb_ikea as R

task, ckpt, rows_f, out = sys.argv[1:5]
bodies = (sys.argv[sys.argv.index("--bodies") + 1] if "--bodies" in sys.argv else "shelf,half_A,half_B,rod,bolt_1").split(",")
z = np.load(rows_f); rows = z["ctrl"]; r0 = int(z["ckpt_row"])
if "--n" in sys.argv:
    rows = rows[:int(sys.argv[sys.argv.index("--n") + 1])]
s = R.Session(task)
idx = json.load(open(os.path.join(ckpt, "index.json")))
c = next(c for c in idx["checkpoints"] if c["row"] == r0)
st = pickle.load(open(os.path.join(ckpt, c["file"]), "rb"))
s.set_state(st)
assert s.state_sha() == c["state_sha"], "checkpoint hash"
s.validity.reset()
ev0 = (len(getattr(getattr(s.S.mech, 'welder', None), 'events', []) or []), len(getattr(s.S.mech, 'arm_events', []) or []))
print('events at checkpoint (welds, arms)', ev0)
m, d = s.model, s.data
bid = {n: m.body(n).id for n in bodies}
robot = set(R.robot_bodies(m).tolist())
table = {g for g in range(m.ngeom) if m.body(m.geom_bodyid[g]).name == "table"}
dt = R.SUBSTEPS * m.opt.timestep
v6 = np.zeros(6); f6 = np.zeros(6)
rec = []
for t, row in enumerate(rows, 1):
    s.step(row)
    W = 0.; rob = []
    for i in range(d.ncon):
        con = d.contact[i]; b1, b2 = int(m.geom_bodyid[con.geom1]), int(m.geom_bodyid[con.geom2])
        for bb, other, sgn in ((b1, b2, -1.), (b2, b1, 1.)):
            if bb in bid.values() and other in robot:
                mujoco.mj_contactForce(m, d, i, f6)
                F = sgn * (con.frame.reshape(3, 3).T @ f6[:3])          # force on bb (frame: geom1 -> geom2 normal)
                mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, bb, v6, 0)
                vp = v6[3:] + np.cross(v6[:3], con.pos - d.xpos[bb])
                W += float(F @ vp) * dt
                rob.append((m.body(bb).name, m.body(other).name, round(float(np.linalg.norm(F)), 1)))
    tab = sorted({m.body(int(m.geom_bodyid[g])).name for i in range(d.ncon) for g in (d.contact[i].geom1, d.contact[i].geom2)
                  if (d.contact[i].geom1 in table or d.contact[i].geom2 in table) and int(m.geom_bodyid[g]) in bid.values()})
    ke = 0.
    rr = dict(t=t)
    for n, b in bid.items():
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, b, v6, 0)
        rr[n] = [round(x, 4) for x in d.xipos[b]] + [round(float(np.linalg.norm(v6[3:])), 3)]
    rr.update(robot_work_j=round(W, 5), robot_contacts=rob[:6], on_table=tab,
              warn={w: int(d.warning[getattr(mujoco.mjtWarning, w)].number) for w in ("mjWARN_BADQACC", "mjWARN_BADQPOS", "mjWARN_BADQVEL")},
              depth_mm=round(1000 * s.validity.max_part_depth_m, 3), breakdown=s.validity.breakdown)
    rec.append(rr)
mech = s.S.mech
ev = dict(welds=getattr(getattr(mech, 'welder', None), 'events', None), arms=getattr(mech, 'arm_events', None),
          eq_active=[int(x) for x in d.eq_active])
json.dump(dict(ckpt_row=r0, rows=len(rows), rec=rec, final_sha=s.state_sha(), mechanism=ev), open(out, "w"), default=str)
print('mechanism', json.dumps(ev, default=str)[:600])
print("done", len(rec), s.state_sha()[:16])
