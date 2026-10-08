# Sim-to-Real (I2RT YAM)

A benchmark of our own whose scenes are **digital twins of a physical robot**, so that what an agent hands in can be
replayed on the real hardware. The robot is I2RT's **YAM bimanual station**: two 6-joint YAM arms with `linear_4310`
parallel grippers, 0.61 m apart on the table top and both facing +x, a RealSense D405 on each wrist and a third on the
gantry above and behind them. The scenes are built from **NVIDIA RoboLab's asset library**: scanned YCB household
objects (which can be bought, so a physical copy of each scene can be set up), RoboLab's grey tote, an oak tabletop and
an indoor HDRI room. `simulator = "mujoco"`, `robot = "i2rt-yam-bimanual"`, tasks
`tasks/sim_to_real-<family>-i00-privileged`. Status: **first two tasks, privileged mode only** (placeholder PR); the
standard twins and the real-robot side are the next steps below.

## Tasks
| family | arms | scene and goal | difficulty | oracle |
|---|---|---|---|---|
| `fruits_in_bowl` | left | a cluttered table (bowl, banana, lemon, orange, mug, soup can); put the banana and the lemon into the bowl | medium | full (692 steps, 13.8 s) |
| `pack_tote` | both | RoboLab's tote between the arms; a soup can and a foam brick on the left, a potted meat can and a marker on the right, each pair out of the other arm's reach; pack all four | medium | full (1370 steps, 27.4 s) |

Neither task gives motion primitives: the agent writes its own IK for a small 6-DoF arm. The YAM's top-down workspace is
small (the gripper points straight down only up to about 0.45 m from its base, and only close to the table), so lifting
over a 10.5 cm tote rim needs tilted approaches. The objects are real shapes: a curved banana whose bounding-box centre
is in the air, a 29 g lemon that rolls, a 16 g marker lying flat. The clutter blocks the 10 cm-wide gripper housing and
the wrist camera. The scripted reference controller solves `fruits_in_bowl` on 8 of 8 random layouts and `pack_tote` on
3 of 6.

## Scene: RoboLab's assets in MuJoCo
- **Assets** (`scripts/sim_to_real/assets/build_assets.py`, run when the image is built): RoboLab v0.3.1's USD assets
  are converted to MuJoCo:
  - each object's scanned mesh with its UVs and texture, downscaled to 1024 px;
  - a CoACD convex decomposition for collision (single-threaded and in canonical order, so a rebuild reproduces it);
  - the mass of the physical YCB object (the YCB set's published masses, not RoboLab's rounded values);
  - the tote's mesh for rendering, with box walls for its collision;
  - RoboLab's Oak texture for the tabletop;
  - the `reading_room_2k` HDRI as six tone-mapped skybox faces.

  `scripts/sim_to_real/assets/manifest.sha256` lists every output file; the image build fails if a rebuild differs.
- **Licences**: only redistributable subsets are used, so the image can be public. YCB (YCB-Video / BOP) is MIT;
  RoboLab's fruits, tote and materials are Apache-2.0; the Poly Haven HDRI is CC0. RoboLab's HOPE and HANDAL objects
  (CC BY-NC-SA) and HOT3D objects (Meta's licence) are not used.
- **RoboLab's scene files** (`assets/scenes/*.usda`) are not used: they reference NVIDIA's online SimReady props
  (crates, carts), which are not in the library. Our scenes are laid out by `rcb_yam.make_instance`: seeded,
  non-overlapping footprints, then 1.5 s of settling, whose poses become the frozen instance.
- **Success** = RoboLab's own `object_in_container`, used for its banana-in-bowl task: the object's centroid lies in the
  container's local bounding box, with one container height of open-top slack above it; the object touches the
  container; the gripper has let go. We add: the container upright, all objects at rest, and no arm-to-arm contact.
- **Rendering**: MuJoCo's rasteriser with textures, a shadow-casting key light and the HDRI as a skybox. It is far from
  path-traced, but it shows readable product labels in the wrist cameras. An RTX-rendered twin would start from ARISE's
  YAMLab USD (Isaac Lab, MIT).

## Why MuJoCo (and not Isaac / RoboLab itself)
- **Robot model**: MuJoCo Menagerie's `i2rt_yam/yam_linear_4310.xml` (MIT, added 2026-10-05, commit f054586) is derived
  from I2RT's SDK v1.3.6, with the SDK's PD gains, gravity compensation, the 0–47.5 mm finger travel with a 5 mm squeeze
  range, finger collision boxes and the wrist D405. The bimanual layout and the top camera follow I2RT's station model
  (`yam_station_linear_4310_d405`, MIT). There is no official YAM USD, and RoboLab supports only Franka/DROID and Kinova.
- **Reproducibility**: CPU physics, bit-exact replay in a fresh process, the same contract as the other MuJoCo tasks.
- **Image**: public, about 1 GB, no GPU needed (OSMesa); a GPU is only for EGL rendering. RoboLab (Isaac Sim 5.1) would
  make the image BUILD_ONLY and RTX-bound.

## Conventions (D7: world-frame quantities are given)
- World frame = the left arm's base frame: +x forward, +y left, +z up, metres; table top z = 0; right base at
  (0, −0.61, 0). Object poses, meshes and masses are readable in privileged mode.
- Start: both arms in the rest pose (all joints 0, folded), grippers fully open — the pose the real arms power up in.
- Control: 50 Hz, 10 physics steps of 2 ms (implicitfast, elliptic cones). Each step takes 14 position targets
  (`left/joint1..6, left/gripper, right/joint1..6, right/gripper`; gripper = finger rail travel in m).
- **Real-robot limits are part of the task**: a rate limit (3 rad/s per joint, 0.25 m/s per gripper) that `step()`
  applies and the verifier re-checks on the recorded rows. **Any arm-to-arm contact fails the trajectory.** The
  deliverable can therefore be sent to the robot unchanged.
- Grading = two replays in fresh sessions with identical final state hashes.

## Generator, instances, oracle
- `scripts/sim_to_real/mk_tasks.py` (`--check`) writes every task dir from `shared/` (the tooling `rcb_yam.py`, the
  grader `grade.py`), `instances/<family>.json`, `oracles/` and its own templates, then runs `task_conventions.normalize`.
- `scripts/sim_to_real/make_instances.py` runs in the image. It lays out and settles each instance from its seed,
  records the initial-state hash, runs the reference controller `oracles/oracle_yam.py`, and checks two fresh-process
  replays (same final hash, success). Hashes recorded on 2026-10-08 with eai-sim_to_real:0.2.0 on an RTX 4090 host:

  | family | seed | instance hash | oracle's final hash |
  |---|---|---|---|
  | `fruits_in_bowl` | 3101 | f94cc026b6fd | 8e31bdfe7bb5 |
  | `pack_tote` | 4202 | 3f80bf4fce9c | 75b09bb28359 |
- The reference controller lives only in `solution/`. It uses DLS IK on the grasp sites, grasps from each object's mesh,
  and approach tilts of 0–50° away from the base.

## Image
`images/sim_to_real/` → `ghcr.io/mll-lab-nu/eai-sim_to_real:<VERSION>` (0.2.0). It builds in two stages:
1. RoboLab v0.3.1 cloned with only the needed LFS files, then converted by `build_assets.py` and checked against the
   manifest.
2. python:3.12-slim (by digest) with MuJoCo 3.3.7 and the pinned closure of its pip packages; Menagerie's `i2rt_yam/`
   at f054586 under `/opt/eai_s2r/menagerie`; the converted assets (24 MB) under `/opt/eai_s2r/assets`.

The image is not pushed yet.

## Next steps
1. **Standard twins** (`eai-standard/2.2`): the robot as a service, with images from the three D405s plus proprioception
   and no reset. This is the mode closest to the real robot; the client API would mirror the I2RT SDK
   (`command_joint_pos`, `get_observations`).
2. **Real side**: buy the YCB items, print a placement mat in the left base frame for each instance, stream the
   trajectory to `i2rt` at 50 Hz (gripper travel / 0.0475 → the SDK's 0–1), score the same predicate by a person or from
   the top camera, and report sim-vs-real success per task.
3. **More families and calibration**: more RoboLab-style scenes (shelf, drawers, kitchen fixtures once a redistributable
   source is found), and identifying the friction loss, the gripper force and the contact parameters on the real station.
