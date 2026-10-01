# RoboLab

[NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 on Isaac Lab 2.3.2 / Isaac Sim 5.1: tabletop language-goal tasks
for a Franka with a Robotiq 2F-85 (DROID joint-position actions). `simulator = "robolab"`, `robot = "franka-robotiq-2f85"`.
88 families, each as a privileged task `robolab-<family>-i00-privileged` and its standard twin `robolab-<family>-i00-standard`.

## Tasks and generators
- Template tasks: `tasks/robolab-banana-in-bowl-i00-privileged` and its standard twin; generators `scripts/robolab_mk_task.py` and
  `scripts/robolab_mk_limited.py`. The frozen instance is the full scene state after RoboLab's canonical seeded reset,
  with its hash; RoboLab's own `success` termination term is the predicate.
- Reference solutions where we wrote one (`solution/`, skills in `solution/ref_primitives.py`); the other families
  declare their oracle level and evidence (PROTOCOL §2.7).

## Image and host
- `images/robolab/` (Isaac Lab 2.3.2 / Isaac Sim 5.1 from the pinned `uv.lock`, RoboLab's Apache-2.0 asset library baked
  in). It contains NVIDIA Isaac Sim, whose licence forbids redistribution: **BUILD_ONLY**, every host builds it
  (`scripts/build_images.sh robolab`; an NVIDIA RTX-class GPU and the Isaac Sim licence terms accepted by the builder).
- Isaac needs an RTX-class GPU even headless (PhysX runs on the CPU). One Isaac simulator at a time on a 32 GB host.
- Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own `*_trusted` cache
  volumes, never the agent's container.

## Time budget (D8)
5400 s for every task of both modes: every Python process pays about 2 minutes of Isaac launch and scene build, so an
agent's iterations cost more than in the default 3600 s budget's simulators.

## Grading and determinism
- PhysX on the CPU: a fresh process reproduces the live run bit for bit, but a second replay inside one process drifts in
  the last bits, so the verifier replays in **two fresh processes** and compares them.
- Standard mode: the service dumps the episode and exits on the collect hook's signal; the hook replays it in two fresh
  processes (`environment/sim/finalize.sh`), `live_matches_replay` reported separately.
- Crash recovery (docs/STANDARD_MODE_2_2.md §13): resume class `exact` (the resumed service is a fresh process; its
  journal replay is that process's first replay). Scene builds measured 98–217 s: the 900 s watchdog default is enough.

## Tooling (file names)
| main's convention | RoboLab |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_robolab.py` (`Session`: the frozen scene state, thin primitives, rendering, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_robolab.py` |
| standard sidecar | `environment/sim/server.py` (2.2 adapter), `run.sh`, `finalize.sh`, `rcb_robolab.py` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records (T, 8) actions (7 joint targets + the binary gripper command) at 15 Hz. Every copy of the tooling and
of the standard sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** Differential-IK moves, joint moves, gripper, hold, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills (grasp, place, navigate) are never added to the agent's tooling;
  reference solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the robot's root frame (Franka base at the origin) is the world convention. Privileged tasks
  give the privileged state through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (8: 7 joints + binary gripper, switched at the row) and `ee_pose` (8, closed-loop differential IK, at most
0.25 m/s, fingertip-centre frame); cameras `egocentric_mirrored_camera`, `over_shoulder_left_camera` (static) and
`wrist_cam` (on the Robotiq base link); Isaac `distance_to_image_plane` depth; `/kinematics` from a numpy model of the USD
joints (7); 32 proprio columns. STANDARD_MODE_2_2.md §16.

## Licences
RoboLab: Apache-2.0 (code and assets); Isaac Lab: BSD-3-Clause on GitHub, its pip wheels and Isaac Sim 5.1 are NVIDIA
proprietary software (no redistribution), hence BUILD_ONLY.
