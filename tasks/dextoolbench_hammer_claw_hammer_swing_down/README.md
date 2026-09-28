# dextoolbench_hammer_claw_hammer_swing_down

DexToolBench task `hammer / claw_hammer / swing_down` (SimToolReal, MIT) ported to plain MuJoCo for this benchmark.

| | |
|---|---|
| source | [SimToolReal / DexToolBench](https://github.com/tylerlum/simtoolreal) @ 313d5ae: object meshes, goal trajectory (37 goals); MuJoCo scene rebuilt from its sim2sim `deployment/mujoco/mujoco_sim.py` |
| robot | KUKA iiwa 14 (MuJoCo Menagerie @ 1b86ece) + left Sharpa HA4 hand, 29 position-controlled joints |
| physics | MuJoCo 3.3.7, 600 Hz, implicitfast, elliptic cones; control 60 Hz (10 substeps) |
| deliverable | `(T, 29)` joint targets per control step; bit-exact replay |
| metric | DexToolBench task progress: goal reached when all 8 grasp-box keypoints are within 1.5 cm; 10 s per goal; reward = goals / 37 |
| oracle | `solution/`: SimToolReal's pretrained policy run in this exact scene (scripts/dtb_mk_oracle.py), recorded targets replayed: 37/37 in 691 control steps; nop 0/37 |
| port check | the policy's final state hash in this scene equals the one in SimToolReal's own MuJoCo sim (b8acca987fcd) |
| egress | allowlist (model APIs only): the pretrained policy is publicly downloadable |
