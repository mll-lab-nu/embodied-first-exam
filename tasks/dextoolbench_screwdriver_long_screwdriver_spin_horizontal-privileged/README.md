# dextoolbench_screwdriver_long_screwdriver_spin_horizontal-privileged

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | privileged |
| Twin | `dextoolbench_screwdriver_long_screwdriver_spin_horizontal-standard` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/screwdriver/long_screwdriver/spin_horizontal` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
DexToolBench task `screwdriver / long_screwdriver / spin_horizontal` (SimToolReal, MIT) ported to plain MuJoCo for this benchmark.

## Difficulty
Dexterous tool use: a KUKA iiwa 14 arm with a 22-DoF Sharpa HA4 hand (29 position-controlled joints) must carry the tool along DexToolBench's goal trajectory, every goal within 1.5 cm on all keypoints, and success needs every goal. SimToolReal's pretrained policy reaches 31/31 goals here.

## Reference solution
`solution/`: SimToolReal's pretrained policy run in this exact scene (scripts/dtb_mk_oracle.py), recorded targets replayed: **31/31 goals** in 1631 control steps (the policy's own sim2sim progress; a task's reference, not a ceiling); nop 0/31

## Verification
DexToolBench task progress: goal reached when all 8 grasp-box keypoints are within 1.5 cm; 30 s per goal (upstream 10 s); `reward.txt` = 1 iff every goal is reached (both replays agreeing); `progress` = goals / 31 in `reward.json`

## Details
| | |
|---|---|
| source | [SimToolReal / DexToolBench](https://github.com/tylerlum/simtoolreal) @ 313d5ae: object meshes, goal trajectory (31 goals); MuJoCo scene rebuilt from its sim2sim `deployment/mujoco/mujoco_sim.py` |
| robot | KUKA iiwa 14 (MuJoCo Menagerie @ 1b86ece) + left Sharpa HA4 hand, 29 position-controlled joints |
| physics | MuJoCo 3.3.7, 600 Hz, implicitfast, elliptic cones; control 60 Hz (10 substeps) |
| deliverable | `(T, 29)` joint targets per control step; bit-exact replay |
| table props | none (plain table) |
| egress | allowlist (model APIs only): the pretrained policy is publicly downloadable |
