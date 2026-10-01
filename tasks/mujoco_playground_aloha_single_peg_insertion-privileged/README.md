# mujoco_playground_aloha_single_peg_insertion-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_aloha_single_peg_insertion-standard` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `mujoco_playground/AlohaSinglePegInsertion` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
MuJoCo Playground's `AlohaSinglePegInsertion` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (peg tip ≤ 5 mm from the socket axis and ≥ 25 % inside (axial t ≤ 0.75) at the end), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: top-down grasps with DLS IK + gravity feedforward, lift, rate-limited visual servo of the peg tip onto the socket axis, push in (tip 1.8 mm from the axis, t = 0.44, 470 control steps)

## Verification
Playground has only a shaped RL reward; defined here from its insertion geometry: peg tip ≤ 5 mm from the socket axis and ≥ 25 % inside (axial t ≤ 0.75) at the end

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/aloha/xmls/mjx_single_peg_insertion.xml`; ALOHA 2 from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 400 Hz (Playground's sim_dt), implicitfast; control 50 Hz (8 substeps) |
| instance | Playground's reset randomization (peg, socket xy ± 0.1 m) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward; defined here from its insertion geometry: peg tip ≤ 5 mm from the socket axis and ≥ 25 % inside (axial t ≤ 0.75) at the end |
| deliverable | `(T, 14)` actuator targets per control step, T ≤ 3000; bit-exact replay |
