# dextoolbench_hammer_mallet_hammer_swing_down

DexToolBench task `hammer / mallet_hammer / swing_down` (SimToolReal, MIT) ported to plain MuJoCo for this benchmark.

| | |
|---|---|
| source | [SimToolReal / DexToolBench](https://github.com/tylerlum/simtoolreal) @ 313d5ae: object meshes, goal trajectory (36 goals); MuJoCo scene rebuilt from its sim2sim `deployment/mujoco/mujoco_sim.py` |
| robot | KUKA iiwa 14 (MuJoCo Menagerie @ 1b86ece) + left Sharpa HA4 hand, 29 position-controlled joints |
| physics | MuJoCo 3.3.7, 600 Hz, implicitfast, elliptic cones; control 60 Hz (10 substeps) |
| deliverable | `(T, 29)` joint targets per control step; bit-exact replay |
| metric | DexToolBench task progress: goal reached when all 8 grasp-box keypoints are within 1.5 cm; 30 s per goal (upstream 10 s); reward = goals / 36 |
| oracle | `solution/`: SimToolReal's pretrained policy run in this exact scene (scripts/dtb_mk_oracle.py), recorded targets replayed: **12/36 goals** in 1453 control steps (the policy's own sim2sim progress; a task's reference, not a ceiling); nop 0/36 |
| table props | one nail (SimToolReal table_narrow_nail) |
| egress | allowlist (model APIs only): the pretrained policy is publicly downloadable |
