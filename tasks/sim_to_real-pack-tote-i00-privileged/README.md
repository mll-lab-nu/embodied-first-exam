# sim_to_real-pack-tote-i00-privileged

| | |
|---|---|
| Benchmark | Sim-to-Real (I2RT YAM) |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `pack_tote` / seed 4202 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-sim_to_real:0.2.0` |

## Task
RoboLab's grey **tote** (42 x 28 x 10.5 cm, 0.6 kg, free to slide) stands between the two arms. On the left arm's outer side: a **tomato soup can** (349 g) and a **foam brick** (28 g); on the right arm's outer side: a **potted meat can** (`spam_can`, 370 g) and a **marker** (16 g). Each pair is out of the other arm's reach; the tote can be reached by both. put all four objects into the tote. The scene is the MuJoCo digital twin of a physical I2RT YAM bimanual station with scanned YCB
objects (physical copies can be bought), built from NVIDIA RoboLab's asset library; the deliverable is a rate-limited
joint trajectory meant to be replayed on the real robot later.

## Difficulty
A bimanual packing task: both arms planned together with no motion primitives, four objects of very different size and weight (a 349 g can, a 16 g marker lying flat), lifts that must clear a 10.5 cm rim although the YAM can point straight down only near the table (higher up the approach has to tilt), drops that land inside the tote without knocking it over or bouncing out, and no arm-to-arm contact ever while both arms work over the same tote. Medium: a scripted controller solves it in about 28 s of robot time, and fails on half of the random layouts it was tried on.

## Reference solution
`solution/oracle_yam.py` (`pack_tote`): the left arm packs its two objects, returns to rest, then the right arm packs its two; mesh-based grasps, approach tilts chosen per waypoint, each object released 2.5 cm above the rim over its own slot in the tote.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` twice from the frozen instance in fresh sessions. In both families an object counts as **in** its container exactly as in NVIDIA RoboLab's `object_in_container`: its centre of mass lies inside the container's bounding box in the container's own frame (with one container height of open-top slack above it) **and** it touches the container. At the **end of the trajectory** every goal object must be in, the container must be upright (within 20 degrees), every object must be at rest (speed below 5 cm/s) and touched by neither robot (the grippers have let go), and the two arms must never have touched each other. `s.check()` (also returned by `s.step`) computes exactly this.
Also required: every row within the joint limits and the rate limit, and both replays ending in the same state hash.

## Details
| | |
|---|---|
| source | robot_coding_bench (this repository): scene layout and task written for this benchmark, success predicate = RoboLab's `object_in_container`; objects, tote, oak texture and HDRI from [NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 assets (YCB: MIT; RoboLab: Apache-2.0; Poly Haven HDRI: CC0), converted by `scripts/sim_to_real/assets/build_assets.py`; YAM arm from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ f054586 `i2rt_yam/yam_linear_4310.xml` (MIT); station extrinsics from [i2rt-robotics/i2rt](https://github.com/i2rt-robotics/i2rt) v1.3.6 (MIT) |
| physics | MuJoCo 3.3.7, 500 Hz, implicitfast, elliptic cones; objects collide through convex hulls (CoACD) and carry the YCB set's measured masses; control 50 Hz (10 substeps); rate limit 3 rad/s (joints), 0.25 m/s (grippers) |
| instance | seed 4202 (`rcb_yam.make_instance`: seeded layout, then 1.5 s of settling): tote at (0.284, -0.316); tomato_soup_can at (0.242, 0.062); foam_brick at (0.334, 0.168); spam_can at (0.222, -0.742); marker at (0.331, -0.645); initial-state hash 3f80bf4fce9c |
| deliverable | `(T, 14)` applied position targets per control step, T ≤ 3000; bit-exact replay |
| sim-to-real | the objects are YCB items that can be bought; the instance's object poses are what a physical setup reproduces (a printed placement mat in the left arm's base frame); the recorded targets go to the I2RT SDK's joint-position command unchanged (gripper: travel / 0.0475 → the SDK's 0–1) |
