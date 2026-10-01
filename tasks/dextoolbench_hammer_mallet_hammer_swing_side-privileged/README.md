# dextoolbench_hammer_mallet_hammer_swing_side-privileged

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | privileged |
| Twin | `dextoolbench_hammer_mallet_hammer_swing_side-standard` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/hammer/mallet_hammer/swing_side` / seed 0 |
| Oracle | `partial` — SimToolReal's pretrained policy, replayed in this scene, reaches 5/32 goals (solution/; README of dextoolbench_hammer_mallet_hammer_swing_side-privileged) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
DexToolBench task `hammer / mallet_hammer / swing_side` (SimToolReal, MIT) ported to plain MuJoCo for this benchmark.

## Difficulty
Dexterous tool use: a KUKA iiwa 14 arm with a 22-DoF Sharpa HA4 hand (29 position-controlled joints) must carry the tool along DexToolBench's goal trajectory, every goal within 1.5 cm on all keypoints, and success needs every goal. SimToolReal's pretrained policy reaches 5/32 goals here.

## Reference solution
`solution/`: SimToolReal's pretrained policy run in this exact scene (scripts/dtb_mk_oracle.py), recorded targets replayed: **5/32 goals** in 922 control steps (the policy's own sim2sim progress; a task's reference, not a ceiling); nop 0/32

## Verification
DexToolBench task progress: goal reached when all 8 grasp-box keypoints are within 1.5 cm; 30 s per goal (upstream 10 s); `reward.txt` = 1 iff every goal is reached (both replays agreeing); `progress` = goals / 32 in `reward.json`

## Details
| | |
|---|---|
| source | [SimToolReal / DexToolBench](https://github.com/tylerlum/simtoolreal) @ 313d5ae: object meshes, goal trajectory (32 goals); MuJoCo scene rebuilt from its sim2sim `deployment/mujoco/mujoco_sim.py` |
| robot | KUKA iiwa 14 (MuJoCo Menagerie @ 1b86ece) + left Sharpa HA4 hand, 29 position-controlled joints |
| physics | MuJoCo 3.3.7, 600 Hz, implicitfast, elliptic cones; control 60 Hz (10 substeps) |
| deliverable | `(T, 29)` joint targets per control step; bit-exact replay |
| table props | one nail (SimToolReal table_narrow_nail) |
| egress | allowlist (model APIs only): the pretrained policy is publicly downloadable |
