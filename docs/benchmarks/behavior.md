# BEHAVIOR-1K

BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 on Isaac Sim 5.1, the stack the 2026 BEHAVIOR Challenge pins): household tasks for
the R1Pro mobile manipulator. `simulator = "behavior"`, `robot = "r1pro"`. 49 challenge tasks, each as a privileged task
`behavior-<family>-i00-privileged` and its standard twin `behavior-<family>-i00-standard`, on a 2026 challenge public_test instance.

## Tasks and generators
- Template tasks: `tasks/behavior-picking-up-trash-i00-privileged` and its standard twin; generators `scripts/behavior_mk_task.py`,
  `scripts/behavior_mk_limited.py` (`scripts/behavior_goal.py` words each BDDL predicate a goal uses, with OmniGibson's thresholds). The predicate is the task's BDDL goal; the
  challenge's timeout is lifted to a runaway guard (time is the budget, not steps).
- Reference solutions where we wrote one; they run the frozen full tooling `solution/rcb_behavior_ref.py` next to the
  robot config. The other families declare their oracle level and evidence (PROTOCOL §2.7).

## Image and host
- `images/behavior/` = the official `stanfordvl/behavior:3.9.2` image **by digest** plus a snapshot-pinned ffmpeg layer
  (`images/behavior/README.md`). It contains Isaac Sim and Omniverse Kit (no redistribution) and a 13.7 GB layer above
  ghcr.io's per-layer limit: **BUILD_ONLY**, every host builds it (`scripts/build_images.sh behavior`).
- The licensed BEHAVIOR dataset is never in an image: every task mounts the host's copy read-only from
  `$RCB_BEHAVIOR_DATA`, a precondition of every BEHAVIOR run (the compose file refuses to start without it).
- An RTX-class GPU; one Isaac simulator at a time on a 32 GB host. torch / OpenMP pools capped at 8 threads (uncapped they
  span every core of a large host and run up to 15× slower). The robot's cameras render at 224×224.

## Time budget (D8)
14400 s for every task of both modes: each Python process pays about 3 minutes of Isaac launch and scene load, and the
simulator runs 7–11 control steps/s, so household tasks of thousands of steps need hours. The standard collect hook may
take 6 h for its two replays of a long episode.

## Grading and determinism
- Determinism is two fresh processes (an in-process reset is approximate): the verifier replays twice and compares.
- Standard mode: the service dumps the episode (artifacts under `/out`, since `/data` is the dataset) and exits; the hook
  replays it in two fresh processes. OmniGibson declares rollouts nondeterministic; measured so far, a live run and its
  fresh replay agree.
- Crash recovery (docs/STANDARD_MODE_2_2.md §13): resume class `approx` (a mismatch is recorded and the episode goes on,
  unless a TCP is more than 0.05 m off). Scene builds measured 130–404 s: set `RCB_STARTUP_TIMEOUT_S` to 1200 (more on
  loaded hosts). A resume replays the episode at ~14–20 steps/s: up to an hour for a long episode.

## Tooling (file names)
| main's convention | BEHAVIOR-1K |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_behavior.py` (`Session`: the frozen instance, thin primitives, the robot's cameras, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_behavior.py` |
| standard sidecar | `environment/sim/server.py` (2.2 adapter), `run.sh`, `finalize.sh`, `rcb_behavior.py`, the robot config |
| reference tooling | `solution/rcb_behavior_ref.py` (frozen; the oracle agent only) |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records 25-D actions (base + trunk + arms + grippers) at 30 Hz.

## Declarations
- **Tooling: thin wrappers only.** Joint moves, a straight-line base drive, cuRobo IK moves, gripper commands and the
  robot's cameras. Task-level skills (grasp, place, navigate) are never added to the agent's tooling; the reference
  solutions keep theirs in `solution/rcb_behavior_ref.py`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the convention that the floor is the plane z = 0 defines the world frame and is given.

## Standard mode (eai-standard/2.2)
`joint_position` (25: base per-step targets in the robot frame, trunk, arms, grippers; base and grippers switch at the
row) and `ee_pose` (16, left first, xyzw, cuRobo IK for both end effectors per row, base still); the head camera and two
wrist cameras (link-mounted, 224×224); OmniGibson `depth_linear`; `/kinematics` on a numpy model of the articulation
(trunk + arms, cuRobo fallback; base frame unless `base_pose` is given); 121 proprio columns. STANDARD_MODE_2_2.md §16.

## Licences
BEHAVIOR-1K code: MIT; the BEHAVIOR Data Bundle: no redistribution (mounted, never copied); Isaac Sim 5.1 and Omniverse
Kit: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Known issues
While the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency).
