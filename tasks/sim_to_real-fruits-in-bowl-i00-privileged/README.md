# sim_to_real-fruits-in-bowl-i00-privileged

| | |
|---|---|
| Benchmark | Sim-to-Real (I2RT YAM) |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `fruits_in_bowl` / seed 3101 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-sim_to_real:0.2.0` |

## Task
A cluttered breakfast table in front of the **left arm**: a red **bowl** (16 cm across, 5.5 cm deep), a **banana**, a **lemon**, an **orange**, a red **mug** and a **tomato soup can**, all scanned household objects (YCB, from RoboLab's asset library) with their real masses (banana 66 g, lemon 29 g). put the **banana** and the **lemon** into the bowl. The other objects may stay where they are. The scene is the MuJoCo digital twin of a physical I2RT YAM bimanual station with scanned YCB
objects (physical copies can be bought), built from NVIDIA RoboLab's asset library; the deliverable is a rate-limited
joint trajectory meant to be replayed on the real robot later.

## Difficulty
Pick-and-place of real object shapes in clutter with one 6-joint arm and no motion primitives: the agent writes its own inverse kinematics, finds grasps on a curved banana (its bounding-box centre is in the air) and on a light, round lemon that rolls when pushed, keeps the 10 cm-wide gripper and the wrist camera clear of the mug and the can next to them, and lets go above a bowl smaller than the banana, all inside the YAM's small top-down workspace (the gripper points straight down only up to about 0.45 m from the base) and under a real-robot rate limit. Medium: a scripted controller solves it in about 14 s of robot time.

## Reference solution
`solution/oracle_yam.py` (`fruits_in_bowl`): damped-least-squares IK on the left arm's grasp site; grasps from each object's mesh (the banana's middle cross-section, the lemon across its narrow side), the approach tilted away from the base where vertical is out of reach; each fruit released 2 cm above the bowl's rim.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` twice from the frozen instance in fresh sessions. In both families an object counts as **in** its container exactly as in NVIDIA RoboLab's `object_in_container`: its centre of mass lies inside the container's bounding box in the container's own frame (with one container height of open-top slack above it) **and** it touches the container. At the **end of the trajectory** every goal object must be in, the container must be upright (within 20 degrees), every object must be at rest (speed below 5 cm/s) and touched by neither robot (the grippers have let go), and the two arms must never have touched each other. `s.check()` (also returned by `s.step`) computes exactly this.
Also required: every row within the joint limits and the rate limit, and both replays ending in the same state hash.

## Details
| | |
|---|---|
| source | robot_coding_bench (this repository): scene layout and task written for this benchmark, success predicate = RoboLab's `object_in_container`; objects, tote, oak texture and HDRI from [NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 assets (YCB: MIT; RoboLab: Apache-2.0; Poly Haven HDRI: CC0), converted by `scripts/sim_to_real/assets/build_assets.py`; YAM arm from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ f054586 `i2rt_yam/yam_linear_4310.xml` (MIT); station extrinsics from [i2rt-robotics/i2rt](https://github.com/i2rt-robotics/i2rt) v1.3.6 (MIT) |
| physics | MuJoCo 3.3.7, 500 Hz, implicitfast, elliptic cones; objects collide through convex hulls (CoACD) and carry the YCB set's measured masses; control 50 Hz (10 substeps); rate limit 3 rad/s (joints), 0.25 m/s (grippers) |
| instance | seed 3101 (`rcb_yam.make_instance`: seeded layout, then 1.5 s of settling): bowl at (0.302, -0.095); banana at (0.243, 0.105); lemon at (0.390, 0.134); orange at (0.363, -0.254); mug at (0.223, -0.242); tomato_soup_can at (0.394, 0.014); initial-state hash f94cc026b6fd |
| deliverable | `(T, 14)` applied position targets per control step, T ≤ 3000; bit-exact replay |
| sim-to-real | the objects are YCB items that can be bought; the instance's object poses are what a physical setup reproduces (a printed placement mat in the left arm's base frame); the recorded targets go to the I2RT SDK's joint-position command unchanged (gripper: travel / 0.0475 → the SDK's 0–1) |
