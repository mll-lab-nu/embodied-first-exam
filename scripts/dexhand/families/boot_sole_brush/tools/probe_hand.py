import json, sys
from pathlib import Path
import numpy as np, mujoco
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
from scene import build
cfg = json.loads((HERE / "task.json").read_text())
m, _ = build(cfg); d = mujoco.MjData(m)
print("nu", m.nu, [m.actuator(i).name for i in range(m.nu)])
print("ctrlrange", m.actuator_ctrlrange.round(2).tolist())
qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
sites = [m.site(i).name for i in range(m.nsite)]
print("sites", sites)
for rot in ([-np.pi/2, 0, 3.13], [0, 0, 0], [np.pi, 0, 0], [0, np.pi/2, 0]):
    q = np.zeros(m.nu); q[3:6] = rot
    d.qpos[:] = 0; d.qpos[qadr] = q; mujoco.mj_forward(m, d)
    palm = d.xpos[m.body("right_hand_C_MC").id]
    R = d.xmat[m.body("right_hand_C_MC").id].reshape(3, 3)
    tips = {n: d.site_xpos[m.site(n).id] - palm for n in sites if "tip" in n.lower()}
    print("rot", np.round(rot, 2), "palm", palm.round(3), "R cols", R.round(2).T.tolist())
    for k, v in tips.items(): print("   ", k, v.round(3))
