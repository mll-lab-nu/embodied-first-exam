# mujoco_playground_panda_open_cabinet-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_panda_open_cabinet-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `mujoco_playground/PandaOpenCabinet` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
MuJoCo Playground's `PandaOpenCabinet` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (handle within 1.5 cm of the target along x at the end), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: to Playground's `home` posture, horizontal approach, pull with correction (3.7 mm, 457 control steps). The recorded solution moves the handle mostly by contact rather than a clean grasp; it still proves the target reachable

## Verification
Playground has only a shaped RL reward; defined here: handle within 1.5 cm of the target along x at the end

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/franka_emika_panda/xmls/mjx_cabinet.xml`; Panda from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 200 Hz (Playground's sim_dt), implicitfast; control 50 Hz (4 substeps) |
| instance | Playground's reset randomization (target x = 0.3 ± 0.1 m; arm start = `upright` + up to 30° per joint) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward; defined here: handle within 1.5 cm of the target along x at the end |
| deliverable | `(T, 8)` actuator targets per control step, T ≤ 3000; bit-exact replay |
