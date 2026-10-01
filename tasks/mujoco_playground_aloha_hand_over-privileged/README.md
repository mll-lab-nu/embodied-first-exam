# mujoco_playground_aloha_hand_over-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_aloha_hand_over-standard` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `mujoco_playground/AlohaHandOver` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
MuJoCo Playground's `AlohaHandOver` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (at the end the box is within 3 cm of the target, touched by the right gripper's fingers only, off the table), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: left top-down grasp, lift to the handover point, right horizontal grasp of the lower half, left release, carry with correction (box 2.5 mm from the target, 650 control steps)

## Verification
Playground has only a shaped RL reward; defined here from it: at the end the box is within 3 cm of the target, touched by the right gripper's fingers only, off the table

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/aloha/xmls/mjx_hand_over.xml`; ALOHA 2 from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 200 Hz (Playground's sim_dt), implicitfast; control 50 Hz (4 substeps) |
| instance | Playground's reset randomization (box xy ± 5 / 10 cm; target (0.2, 0, 0.25) ± 15 cm, x ≥ 0.15) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward; defined here from it: at the end the box is within 3 cm of the target, touched by the right gripper's fingers only, off the table |
| deliverable | `(T, 14)` actuator targets per control step, T ≤ 3000; bit-exact replay |
