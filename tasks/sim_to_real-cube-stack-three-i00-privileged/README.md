# sim_to_real-cube-stack-three-i00-privileged

| | |
|---|---|
| Benchmark | Sim-to-Real (I2RT YAM) |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `cube_stack_three` / seed 1101 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-sim_to_real:0.1.0` |

## Task
Three 4 cm wooden cubes (40 g) — **blue**, **green** and **red** — lie on the table in front of the left arm, each at its own position and yaw. Build a tower: **green on top of blue, red on top of green**, with the blue cube where it is or anywhere else on the table. The scene is the MuJoCo digital twin of a physical I2RT YAM
bimanual station; the deliverable is a rate-limited joint trajectory meant to be replayed on the real robot later.

## Difficulty
Two precise pick-and-place moves with one 6-joint arm and no motion primitives: the agent writes its own inverse kinematics, finds grasps that are reachable (the YAM's top-down workspace is small: the gripper can point straight down only up to about 0.45 m from the base, and only near the table), grasps 4 cm cubes between 1.4 x 1.6 cm finger pads, and places each cube within 2 cm on the one below without knocking the tower over, under a real-robot rate limit. Medium: a scripted IK controller solves it in about 16 s of robot time.

## Reference solution
`solution/oracle_yam.py` (`cube_stack_three`): damped-least-squares IK on the left arm's grasp site, top-down grasps aligned with each cube's faces, green then red placed 4 mm above their resting height and released; 785 control steps (15.7 s).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` twice from the frozen instance in fresh sessions. Success =
at the **end of the trajectory**: the blue cube rests on the table (its centre within 1 cm of z = 0.02), the green cube's centre is within 2 cm horizontally of the blue cube's and 4 cm (± 1 cm) above it, the red cube likewise on the green one; all three cubes are at rest (speed below 5 cm/s) and no part of either robot touches any cube. Also required: every row within the joint limits and
the rate limit, and both replays ending in the same state hash.

## Details
| | |
|---|---|
| source | robot_coding_bench (this repository): scene and success rule written for this benchmark; YAM arm from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ f054586 `i2rt_yam/yam_linear_4310.xml` (MIT); station extrinsics from [i2rt-robotics/i2rt](https://github.com/i2rt-robotics/i2rt) v1.3.6 `yam_station_linear_4310_d405` (MIT) |
| physics | MuJoCo 3.3.7, 500 Hz, implicitfast; control 50 Hz (10 substeps); rate limit 3 rad/s (joints), 0.25 m/s (grippers) |
| instance | seed 1101 (`rcb_yam.make_instance`): cube_blue at (0.3443, 0.0866) yaw 0.3173 rad; cube_green at (0.2299, -0.0475) yaw 0.5628 rad; cube_red at (0.3341, -0.0229) yaw 0.62 rad; initial-state hash e2b97211aead |
| deliverable | `(T, 14)` applied position targets per control step, T ≤ 3000; bit-exact replay |
| sim-to-real | the instance's object poses are what a physical setup reproduces (a printed placement mat in the left arm's base frame); the recorded targets go to the I2RT SDK's joint-position command unchanged (gripper: travel / 0.0475 → the SDK's 0–1) |
