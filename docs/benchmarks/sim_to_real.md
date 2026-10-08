# Sim-to-Real (I2RT YAM)

A benchmark of our own whose scenes are **digital twins of a physical robot**, so that what an agent hands in can be
replayed on the real hardware. The robot is I2RT's **YAM bimanual station**: two 6-joint YAM arms with `linear_4310`
parallel grippers, 0.61 m apart on the table top and both facing +x, a RealSense D405 on each wrist and a third on the
gantry above and behind them. `simulator = "mujoco"`, `robot = "i2rt-yam-bimanual"`, tasks
`tasks/sim_to_real-<family>-i00-privileged`. Status: **first two tasks, privileged mode only** (placeholder PR); the
standard twins and the real-robot side are the next steps below.

## Tasks
| family | arms | what | difficulty | oracle |
|---|---|---|---|---|
| `cube_stack_three` | left | stack three 4 cm cubes, blue → green → red, from scattered seeded poses | medium | full (785 steps) |
| `handover_to_bin` | both | a 4 × 4 × 10 cm block beyond the right arm's reach goes into a bin beyond the left arm's reach: a handover | medium | full (822 steps) |

Both tasks avoid motion primitives on purpose: the agent writes its own IK on a small 6-DoF arm. The YAM's top-down
workspace is small (the gripper points straight down only up to about 0.45 m from its base, and only close to the table).
Grasps have to fit between 1.4 × 1.6 cm finger pads, and the bimanual task needs the arms to share a narrow overlap
without ever touching.

## Why MuJoCo (and not Isaac / RoboLab)
- **Robot model**: MuJoCo Menagerie's `i2rt_yam/yam_linear_4310.xml` (MIT, added 2026-10-05, commit f054586) is derived
  from I2RT's SDK v1.3.6. It carries the SDK's PD gains, gravity compensation, the 0–47.5 mm finger travel with a 5 mm
  squeeze range, finger collision boxes fitted to the meshes, and the wrist D405 at I2RT's CAD extrinsics. The bimanual
  layout and the top camera follow I2RT's own station model (`i2rt/robot_models/station/yam_station_linear_4310_d405`,
  MIT). No official USD exists. ARISE's YAMLab (Isaac Lab 2.3.2, MIT) has a community USD, which is the starting point
  if we ever want an RTX-rendered twin.
- **Reproducibility**: CPU physics, bit-exact replay in a fresh process, the same contract as the other MuJoCo tasks.
- **Image**: Apache-2.0 + MIT, so `eai-sim_to_real` can be public, about 1 GB, and runs without a GPU (OSMesa); a GPU is
  only for EGL rendering. RoboLab (Isaac Sim 5.1) would make the image BUILD_ONLY and RTX-bound. RoboLab supports only
  Franka/DROID and Kinova, so adding the YAM means writing an `ArticulationCfg` plus a USD.
- **From RoboLab** we keep the task style (tabletop goals with a programmatic predicate, seeded frozen instance,
  success = the scene's own predicate) and its rule that the gripper must have let go of the object for success.

## Scene and conventions (D7: world-frame quantities are given)
- World frame = the left arm's base frame: +x forward, +y left, +z up, metres; table top z = 0; right base at
  (0, −0.61, 0). The instruction gives these, and the object poses are readable in privileged mode.
- Start: both arms in the rest pose (all joints 0, folded), grippers fully open — the pose the real arms power up in.
- Control: 50 Hz, 10 physics steps of 2 ms (Menagerie's timestep, implicitfast). Each step takes 14 position targets
  (`left/joint1..6, left/gripper, right/joint1..6, right/gripper`; gripper = finger rail travel in m).
- **Real-robot limits are part of the task**: a rate limit (3 rad/s per joint, 0.25 m/s per gripper) that `step()`
  applies and the verifier re-checks on the recorded rows. **Any arm-to-arm contact fails the trajectory.** The
  deliverable can therefore be sent to the robot unchanged.
- Success = the family's predicate at the end of the trajectory, the objects at rest (< 5 cm/s), touched by neither
  robot. Grading = two replays in fresh sessions with identical final state hashes.

## Generator, instances, oracle
- `scripts/sim_to_real/mk_tasks.py` (`--check`) writes every task dir from `shared/` (the tooling `rcb_yam.py`, the
  grader `grade.py`), `instances/<family>.json`, `oracles/` and its own templates, then runs `task_conventions.normalize`.
- `scripts/sim_to_real/make_instances.py`, run in the image, draws each instance from its seed (`rcb_yam.make_instance`),
  records the initial-state hash, runs the reference controller `oracles/oracle_yam.py`, and checks two fresh-process
  replays (same final hash, success). The hashes recorded on 2026-10-07 (eai-sim_to_real:0.1.0, RTX 4090 host):
  `cube_stack_three` instance e2b97211aead → oracle final 89cfada9e765; `handover_to_bin` 1e92b1e4d215 → f6a476671249.
- The reference controller (DLS IK on the grasp sites, Cartesian waypoints, scripted grasps) lives only in `solution/`.

## Image
`images/sim_to_real/` → `ghcr.io/mll-lab-nu/eai-sim_to_real:<VERSION>` (0.1.0): python:3.12-slim (by digest), MuJoCo
3.3.7 and the pinned closure of its pip packages, Menagerie's `i2rt_yam/` at f054586 under `/opt/eai_s2r/menagerie`.
Not pushed yet.

## Next steps
1. **Standard twins** (`eai-standard/2.2`): the robot as a service, with images from the three D405s plus proprioception
   and no reset. This is the mode closest to the real robot; the client API would mirror the I2RT SDK
   (`command_joint_pos`, `get_observations`).
2. **Real side**: a placement mat printed in the left base frame for each instance, a replay script that streams a
   trajectory to `i2rt` at 50 Hz (gripper travel / 0.0475 → the SDK's 0–1), the same success predicate scored by a
   person or from the top camera, and sim-vs-real success reported per task.
3. **Calibration**: identify the friction loss, the gripper force and the object masses on the real station, and add
   more families (articulated objects, deformables) once the first pair transfers.
