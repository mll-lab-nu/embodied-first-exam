# mujoco_playground_panda_pick_cube_orientation-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_panda_pick_cube_orientation-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `mujoco_playground/PandaPickCubeOrientation` / seed 60417 (allowed seeds: [60417, 60418, 60419]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` |

## Task
MuJoCo Playground's `PandaPickCubeOrientation` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (box within 2 cm and 15° of the target at the end), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: top-down grasp, lift, move the held box onto the target pose with corrections (3 mm, 0.9°, 427 control steps)

## Verification
Playground has only a shaped RL reward (position 0.9 + rotation 0.1); defined here: box within 2 cm and 15° of the target at the end

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 8192 | 6 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 6 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/franka_emika_panda/xmls/mjx_single_cube.xml`; Panda from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 200 Hz (Playground's sim_dt), implicitfast; control 50 Hz (4 substeps) |
| instance | Playground's reset randomization (box xy ± 0.2 m; target xy ± 0.2 m, z + 0.2..0.4 m, tilt ≤ 45°) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward (position 0.9 + rotation 0.1); defined here: box within 2 cm and 15° of the target at the end |
| deliverable | `(T, 8)` actuator targets per control step, T ≤ 3000; bit-exact replay |
