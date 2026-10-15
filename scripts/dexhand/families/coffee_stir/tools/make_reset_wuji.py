"""Authoring only (not shipped): the Wuji Hand 2.2 start state of coffee_stir.

No Wuji pinch of the upright-held spoon exists yet, so with Wuji selected the spoon starts leaning in the mug (bowl on
the mug floor, handle on the rim: the wave-2 start) and the right Wuji hand starts open about 0.25 m above the mug
(palm down), the left arm parked. The scene is settled for 2 s under the held targets (gravity feed-forward on the arm
servos) and written to task.json ``initial_qpos["wuji"]`` / ``initial_targets["wuji"]``.
"""
import json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path.insert(0, str(FAMILY)); sys.path.insert(1, str(HERE))
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
import scene
from scene import arm_rig
from armctl import arm_ik
from make_reset import LEAN_SPOON

path = FAMILY / "task.json"
cfg = json.loads(path.read_text())
cfg_auth = dict(cfg, spoon_pos=LEAN_SPOON)
m, _ = scene.build(cfg_auth, hand="wuji")
d = mujoco.MjData(m)
target = arm_rig.default_targets(m)
lay = arm_rig.layout(m)
R = np.column_stack([[0, 0, -1], [0, 1, 0], [1, 0, 0]]).astype(float)  # palm down, fingers +x
q, ep, er = arm_ik.ArmIK(m, "right").solve_best(np.array([0.36, 0.015, 1.05]), R, qpos=d.qpos)
target[lay["arm"]["right"]] = q
qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
dof = m.jnt_dofadr[m.actuator_trnid[:, 0]]
gain = m.actuator_gainprm[:, 0]
d.qpos[qadr] = target
mujoco.mj_forward(m, d)
lo, hi = m.actuator_ctrlrange.T
arm = np.arange(14)
for _ in range(1000):
    ctrl = target.copy()
    ctrl[arm] += d.qfrc_bias[dof[arm]] / gain[arm]
    d.ctrl[:] = np.clip(ctrl, lo, hi)
    mujoco.mj_step(m, d)
sp = m.body("spoon").id
v = np.zeros(6)
mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, sp, v, 0)
print("ik", round(ep, 4), round(er, 4), "spoon", np.round(d.xpos[sp], 4).tolist(), "speed", float(np.linalg.norm(v[3:])),
      "hand", np.round(d.xpos[m.body("wrist_stage").id], 3).tolist())
cfg = json.loads(path.read_text())
cfg.setdefault("initial_qpos", {})["wuji"] = [float(x) for x in d.qpos]
cfg.setdefault("initial_targets", {})["wuji"] = [float(x) for x in d.ctrl]
path.write_text(json.dumps(cfg, indent=1) + "\n")
print("wrote", path)
