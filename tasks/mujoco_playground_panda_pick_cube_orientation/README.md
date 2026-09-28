# mujoco_playground_panda_pick_cube_orientation

MuJoCo Playground's `PandaPickCubeOrientation` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/franka_emika_panda/xmls/mjx_single_cube.xml`; Panda from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 200 Hz (Playground's sim_dt), implicitfast; control 50 Hz (4 substeps) |
| instance | Playground's reset randomization (box xy ± 0.2 m; target xy ± 0.2 m, z + 0.2..0.4 m, tilt ≤ 45°) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward (position 0.9 + rotation 0.1); defined here: box within 2 cm and 15° of the target at the end |
| deliverable | `(T, 8)` actuator targets per control step, T ≤ 3000; bit-exact replay |
| oracle | `solution/oracle_ik.py`: top-down grasp, lift, move the held box onto the target pose with corrections (3 mm, 0.9°, 427 control steps) |
