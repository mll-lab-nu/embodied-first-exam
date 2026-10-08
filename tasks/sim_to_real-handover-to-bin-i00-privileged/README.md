# sim_to_real-handover-to-bin-i00-privileged

| | |
|---|---|
| Benchmark | Sim-to-Real (I2RT YAM) |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `handover_to_bin` / seed 2202 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-sim_to_real:0.1.0` |

## Task
An orange **block** (4 x 4 x 10 cm, 80 g) stands upright on the table at the left arm's outer side, beyond the right arm's reach. An open grey **bin** (16 x 16 cm inside, walls 6 cm high, 1 cm thick) is fixed to the table at the right arm's outer side, beyond the left arm's reach. Get the block into the bin. Neither arm can do it alone: the left arm has to pass the block to the right arm (a handover in the air, or putting it down where the right arm can reach it), and the right arm puts it into the bin. The scene is the MuJoCo digital twin of a physical I2RT YAM
bimanual station; the deliverable is a rate-limited joint trajectory meant to be replayed on the real robot later.

## Difficulty
A bimanual task: two arms planned together with no motion primitives, a handover between two small 6-joint arms whose dexterous workspaces barely overlap (top-down grasps reach only about 0.45 m from each base, the bases are 0.61 m apart), grasps that leave room for the other gripper, and no arm-to-arm contact ever (the wrist cameras stick out). Medium: a scripted IK controller solves it in about 16 s of robot time.

## Reference solution
`solution/oracle_yam.py` (`handover_to_bin`): the left arm grasps the block's top from above and carries it to a handover point between the arms; the right arm, waiting beside it, grasps the lower half from behind (approach +x), the left arm lets go and slides out, the right arm carries the block over the bin and lets go 4 cm above the rim; 822 control steps (16.4 s).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` twice from the frozen instance in fresh sessions. Success =
at the **end of the trajectory**: the block's centre is inside the bin's inner walls and less than 11 cm above the bin's base (so the block stands or lies on the bin floor), the block is at rest (speed below 5 cm/s), no part of either robot touches it, and the two arms never touched each other. Also required: every row within the joint limits and
the rate limit, and both replays ending in the same state hash.

## Details
| | |
|---|---|
| source | robot_coding_bench (this repository): scene and success rule written for this benchmark; YAM arm from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ f054586 `i2rt_yam/yam_linear_4310.xml` (MIT); station extrinsics from [i2rt-robotics/i2rt](https://github.com/i2rt-robotics/i2rt) v1.3.6 `yam_station_linear_4310_d405` (MIT) |
| physics | MuJoCo 3.3.7, 500 Hz, implicitfast; control 50 Hz (10 substeps); rate limit 3 rad/s (joints), 0.25 m/s (grippers) |
| instance | seed 2202 (`rcb_yam.make_instance`): block at (0.3166, 0.2145) yaw -0.2228 rad; bin at (0.2913, -0.8124) yaw 0.1518 rad; initial-state hash 1e92b1e4d215 |
| deliverable | `(T, 14)` applied position targets per control step, T ≤ 3000; bit-exact replay |
| sim-to-real | the instance's object poses are what a physical setup reproduces (a printed placement mat in the left arm's base frame); the recorded targets go to the I2RT SDK's joint-position command unchanged (gripper: travel / 0.0475 → the SDK's 0–1) |
