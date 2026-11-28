# RoboARC

## Overview

RoboARC is long-horizon physical manipulation on MuJoCo 3.14.0: topological puzzles (wire, ring and cast puzzles,
claws, knots, ropes, fibers, cloth, a lock) and an IKEA furniture-assembly suite. Each task is one frozen scene, a robot
and a grader that decides from the simulated state whether the task was done. Every base ships in two modes,
privileged and standard: 106 bases, 212 task directories.

```bash
harbor run -d embodied-first-exam@all -p tasks/roboarc -a codex -m <model>
```
Every image is public: Harbor pulls it.

| | |
|---|---|
| upstream | [RoboARC](https://github.com/mll-lab-nu/RoboARC) @ `153eb8c` (RoboARC 1.0.0), MIT |
| puzzle tasks | `tasks/roboarc/roboarc-<family>-<NN>-i01-{privileged,standard}`: 14 families, 98 bases |
| IKEA tasks | `tasks/roboarc/roboarc-ikea-<item>-i00-{privileged,standard}`: 8 items |
| robots | ALOHA 2 (two ViperX 300 s arms), a Franka Panda with a Robotiq 2F-85, two Franka Pandas with the Panda hand |
| time limit | 3 h in every task (`[agent] timeout_sec` = 10800) |
| puzzle image | `ghcr.io/mll-lab-nu/efe:roboarc-<images/roboarc/VERSION>` (`images/roboarc/`); the shared task files come from `ghcr.io/mll-lab-nu/efe:roboarc-files-<version>` (`images/roboarc-files/`, built from `embodied_first_exam/benchmarks/roboarc/`) |
| IKEA images | `ghcr.io/mll-lab-nu/efe:ikea-mujoco-<images/ikea-mujoco/VERSION>` (privileged agent and verifier) and `ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-<images/ikea-mujoco/sim/VERSION>` (the standard `sim` service) |
| GPU | an NVIDIA GPU with RT cores (Nyx rendering); see Interface |

Code identifiers keep the simulator's name: the package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables,
the family keys (`interlocked_claws`) and, inside the image, `/opt/robotangle/` (the instances and
`stage_instance.py`).

## Upstream and license

[RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), MIT License. The simulator source these
tasks run (`/opt/topogym/topogym/`, pruned) is RoboARC 1.0.0's `source/topogym` at `153eb8c`: its `SOURCE.json`
sha256 is `c9171f79…`, the runtime source every task's `runtime_binding.json` names. The image was built from the
same source (`images/roboarc/release.json`, `release_commit`). The IKEA scenes (`images/ikea-mujoco/scenes/<item>/`:
models, mechanisms and success checks) are RoboARC's IKEA suite.

Third-party material, none under non-commercial terms:
- robot models from MuJoCo Menagerie: ALOHA 2 (BSD-3-Clause, Trossen Robotics), Franka Emika Panda (Apache-2.0),
  Robotiq 2F-85 (BSD-2-Clause, ROS-Industrial);
- the IKEA furniture part meshes: CC BY 4.0, from the public Hugging Face dataset `MLL-Lab/embodied-first-exam-public`
  (`ikea-mujoco/`) at a pinned revision (`images/ikea-mujoco/assets.json`);
- MuJoCo 3.14.0 (Apache-2.0); the Nyx renderer (`gs-nyx`, redistributed in the images with its owners' permission);
  Poly Haven's CC0 studio HDRI and textures;
- puzzle designs modelled after Hanayama's Huzzle Cast puzzles, and the IKEA product names and designs: used with the
  owners' permission.

## Changes from upstream

The puzzle families run RoboARC's own tasks, physics and predicates, unchanged. The changes are in the IKEA suite and
in what the tasks add around the simulator:

- **Frozen instances.** Each base is one frozen scene. Its files are in the public image
  (`/opt/robotangle/instances/<base>/`, pinned file by file in `images/roboarc/assets.json`); `stage_instance.py`
  copies a task's instance next to its `runtime_binding.json`, and every Session checks it again.
- **CPU determinism.** Physics runs on the CPU in float64 (the blanket families' cloth: a deterministic CUDA VBD step).
  Every container that runs a Session masks numpy / OpenBLAS SIMD (`NPY_DISABLE_CPU_FEATURES` without AVX-512,
  `OPENBLAS_CORETYPE=Haswell`), so every CPU class builds the same frozen bytes; unmasked, a reference diverged
  between AVX-512 and AVX2 hosts.
- **IKEA physics against the source scenes** (one rule for all scenes, clamp not fail):
  - MuJoCo 3.14.0 with the EPA fix byte-patched in (`images/ikea-mujoco/mujoco-3.14.0-epa/`, 14 bytes of the wheel's
    `libmujoco.so`, backporting upstream MuJoCo `6d662aed`): 3.14.0's EPA writes past two fixed 24-entry arrays, which
    a dowel pressed deep into eket's side panel triggers (a crash or silent memory corruption, about 1 in 400 random
    eket episodes). The patched library is bit-identical to the stock wheel on every reference and stress episode
    checked;
  - every cylinder a robot geom can touch is a 32-facet convex prism at scene build (inscribed in the cylinder);
  - joint-speed clamp: every arm joint target moves at most the robot's real joint velocity limit per control step
    (Franka Panda 2.175 rad/s on joints 1-4 and 2.61 rad/s on joints 5-7; ViperX 300 s 3.14159 rad/s;
    `rcb_ikea.Session.applied()`, in the tooling and the replay alike); a faster row is spread over the following
    control steps, and the gripper command is not limited;
  - eket's dowels: the soft dowel shells touch only the side panels; a stiff copy meets everything else;
  - identical parts are interchangeable (`rcb_ikea.IDENTICAL_PARTS`: VESKEN, STEGESUND, GLADOM, EKET): any of them may
    take any of their places, one part per place. The source graders bound every place to one named part;
  - EKET's end pose: every panel, the back included, must end within 10 mm and 2 degrees of its goal relative to the top
    panel (`rcb_ikea.END_POSE_RULES`); the source grader checks the back only at its slide.
- **IKEA terminal rules**, added on top of each scene's `success.py` in every IKEA task: the parts released, every
  part at rest (at most 0.01 m/s and 0.05 rad/s), no breakdown (no non-finite state, no MuJoCo BADQACC / BADQPOS /
  BADQVEL warning, no part contact deeper than 10 mm), at the end and again after the last row is held 1.0 s more.
- **Added.** The standard mode (a `sim` service with cameras, proprioception and safety readings), the privileged
  tooling (`rcb_topogym.py`, `rcb_ikea.py`), the graders and the references.

## Interface

- **Privileged mode.** The tooling (`/opt/tools/rcb_topogym.py`, or `rcb_ikea.py` for the IKEA suite) gives the full
  simulator on the frozen instance: privileged state, unlimited resets, recording, the verifier's own replay and
  rendering. The deliverable is `/app/output/trajectory.npz`: joint-target rows, one per control step (puzzles:
  `actions` with the instance's `action_layout`; IKEA: `ctrl`, the scene's actuators, 4 physics steps per row). Its row
  cap is stated in each instruction (the verifier's replay must fit its time limit).
- **Standard mode.** The robot is a service in the `sim` sidecar, reached through `/opt/tools/rcb_client.py` or the
  `efe-robot` MCP tools; the standard tasks follow eai-standard/3.0 (agent-ended episodes: the agent ends the episode
  with `/finish`). Actions: `joint_position` chunks at the task's control rate and, in the puzzle families, `ee_pose`
  rows (IK per row); the IKEA suite offers `joint_position` only, with stateless FK / IK in `/kinematics`.
  Observations: four cameras (`cam_high`, `cam_low` static, one on each wrist; the single-arm families have their own
  set), 848 × 480 RGB from Nyx, optional depth, calibration with every frame, proprioception and, in the puzzle
  families, the safety readings below. No object poses, no reward, no success signal; no reset.
- **World-frame information.** The standard tasks' texts give no world coordinates: no object poses or positions, no
  table height, no world position of the robot base. Every pose the standard agent gets or gives is in the robot frame
  (puzzles: origin at the robot's root link on its mounting; IKEA: at the left arm's base link; +z up), which every
  text calls the world frame. Physics, graders and state hashes do not depend on it. Privileged mode keeps the
  simulator's world frame; its texts state no table height or base position either.
  `ci_checks/check-world-frame-texts.sh` checks the standard texts.
- **Safety readings** (`meta["safety"]`, puzzle families, every response). The physical-validity rules judge the agent
  on these readings, so the agent sees them. They are exactly what `rcb_topogym._SafetyMonitor.read` returns (maxima
  since the previous response, each next to its limit), never a pose:

  | Field | What it is | Families |
  |---|---|---|
  | `rules`, `scope` | the policy's revision; "since the previous read" | all |
  | `forcing` | the largest pressing force of a gripper or a held part, the drive fraction while pressing, the longest forcing time, the events and the thresholds | all |
  | `task_contact_mm` | the deepest contact between task parts, the longest time above the sustained limit, the review and breakdown limits | rigid |
  | `held_finger_contact_mm` | the deepest contact between a finger and the part it holds, with its review limits | rigid |
  | `review` | the count of review events and the last three (kind, control step, the two parts, depth, force) | rigid |
  | `soft_volume_ratio` | the lowest volume ratio of each soft body and the longest time at or below 0 | soft |
  | `attachment_stretch_mm` | the worst cord attachment stretch and the longest time above its limit | soft |
  | `table_guard` | the control steps whose gripper target the table guard stopped | where the guard applies |
  | `ik_jumps` | the last IK solutions far from the current joints (`ee_pose`) | when one occurred |

- **Robot safety (puzzle tooling, both modes).** No gripper target goes lower than 15 mm below the tabletop; arm drive
  torques are capped; an arm more than 5 mm deep in a fixed object is stopped where it is for that control step.
- **Grasping.** Puzzle families use assisted grasping where the instance declares grasp regions (the rule is in each
  instruction: the weld's slip force over 20 ms, 60 N for ALOHA and 65 N for the Robotiq); the IKEA suite uses physical
  grasps only (finger friction).
- **GPU.** Nyx needs an NVIDIA GPU with RT cores and the driver's Vulkan / EGL user-space libraries (driver 580 or
  newer), and exactly one visible GPU per container; GPUs without RT cores (A100, H100) cannot run these tasks. Puzzle
  tasks: the GPU is held by `main` in privileged mode and by `sim` in standard mode. IKEA: the privileged agent and
  verifier run on the CPU; the standard `sim` service renders on the GPU.

## Grading

The verdict comes from the simulated state only. Each task's README states its conditions and thresholds exactly.

- **Puzzle families, the predicate.** RoboARC's own predicate of the task, with the frozen instance's thresholds,
  must hold for the family's confirmation window (0.5 s; buzz-wire-3d 1 s; hedgehog-in-cage 2 s). The task's failure
  predicates (a piece below the table, a fine fiber touched, a metal touch of the buzz wire, a chain unhooked, a rotor
  past its stop, the cord loop broken) end the episode with 0.
- **Puzzle families, privileged.** `tests/grade.py` replays the trajectory once in a fresh process. The episode ends at
  the first success or failure; success must be reached within the delivered rows. The six families with a grading
  hold (blanket-flatten, knot-untying, lock-picking, orbits, rope-threading, slotted-post-ring;
  `rcb_topogym.REPLAY_TOLERANCES`) also hold the last targets for up to 2 s after the rows, with thresholds loosened
  by small slacks set from replay-to-replay spreads measured on recorded agent trajectories; a success reached only in
  that hold is recorded (`success_in_hold_only`) and not credited.
- **Puzzle families, standard.** The live episode is the verdict; nothing is replayed. A success never ends the
  episode and is never shown. At `/finish`, at the end of the agent's session or at the 200,000-step runaway guard, the
  predicate must hold and keep holding, with the last targets held, for the rest of the confirmation window (the time
  it already held counts). The service raises the task's own `stable_duration_s` out of reach and counts the window
  itself from the task's per-tick `_goal_active`; a task without them refuses to start (`agent_end_unsupported`, an
  infrastructure error). After the verdict, one video-only replay renders `replay.mp4`; it never changes the verdict.
- **Review and forcing.** A success with a deep task contact (`rcb_topogym.CONTACT_RULE`: deeper than 3 mm, or than
  2 mm for 0.25 s; a finger on a held part 4 mm) is held for human review: it scores 0 and is flagged, with the
  events and frames around them. Forcing (an arm drive at 95 % of its torque cap while its gripper or a held part
  presses with 20 N or more) is evidence only. A simulator breakdown (a non-finite state, a task contact deeper than
  10 mm, a MuJoCo instability) is an infrastructure error, unless an arm was forcing in the 0.25 s before it: then it
  is the agent's failure (`forced_breakdown`).
- **IKEA suite.** One rule in both modes: the scene's `success.py`, plus the terminal rules (released, at rest, no
  breakdown), at the end and again after the last row is held 1.0 s more (`rcb_ikea.Session.final_check()`).
  Privileged: every row of the trajectory is replayed open-loop in a fresh process. Standard: the live end state at
  `/finish` or at the end of the session; a breakdown or a simulator error ends the episode with 0. A replay that
  crashes or raises in the scene's code is a breakdown, the agent's 0, never a grader error.
- **Clock (standard).** The service counts the time limit from the agent's first request (`RCB_WALL_CLOCK_S` = 10800,
  `meta["time_left_s"]`) and ends the episode with reason `timeout` when it runs out, never before the harness's
  cutoff; that end is judged like the end of the session.
- **Start state and infrastructure.** The privileged verifier checks the rebuilt scene against `tests/runtime_binding.json`
  (files and initial-state hash); the standard service does the same before the episode begins. A mismatch, a give-up
  after crashes between the agent's calls and an unfinalized `final.json` are infrastructure errors (`infra_error` 1),
  never the agent's 0.

## Tasks

| family | bases | robot | goal |
|---|---:|---|---|
| `blanket_flatten` | 8 | ALOHA 2 | unfold the blanket flat on the table |
| `blanket_fold` | 5 | ALOHA 2 | fold the blanket as the target images show |
| `buzz_wire_3d` | 10 | Franka + Robotiq 2F-85 | guide the loop along the whole wire without a metal touch |
| `cast_coil` | 8 | ALOHA 2 | fit the gold and silver pieces together |
| `cast_keyhole` | 6 | ALOHA 2 | take the keyhole piece out and into the goal square |
| `fiber_bundling` | 10 | Franka + Robotiq 2F-85 | feed every fine fiber and the sheath through the ring |
| `hedgehog_in_cage` | 8 | Franka + Robotiq 2F-85 | take the ball (star, owl) out of the cage and into the goal square |
| `horseshoe_ring` | 5 | ALOHA 2 | free the removable ring into the goal square |
| `interlocked_claws` | 12 | ALOHA 2 | separate the pieces, or move one into the goal square |
| `knot_untying` | 7 | ALOHA 2 | untangle the rope flat on the table |
| `lock_picking` | 5 | Franka + Robotiq 2F-85 | pass the key through every rotor plate and the END plate |
| `orbits` | 1 | ALOHA 2 | free the cord and handle into the goal square |
| `rope_threading` | 8 | ALOHA 2 | thread the rope through the holes in order and direction |
| `slotted_post_ring` | 5 | ALOHA 2 | free the metal ring into the goal square |

- Names: `roboarc-<family>-<NN>-i01-<mode>`, the family with dashes; `<NN>` is the base's number in its family, never
  reused (a removed base leaves a gap); `i01` is the MuJoCo instance.
- Reference solutions: every task has one (`oracle = "full"`). Privileged: `solution/trajectory.npz` (its sha256 is
  the one `images/roboarc/release.json` names). Standard: the same rows streamed through the client.

### IKEA suite

The IKEA furniture-assembly tasks (`roboarc-ikea-<item>-i00-{privileged,standard}`, one frozen scene per item) share
the `roboarc-` prefix, this folder and the 3 h time limit. Everything else is their own: the tooling `rcb_ikea.py`, the
scenes, the graders and the sim service (source `embodied_first_exam/benchmarks/roboarc/ikea/`), and the images in
`images/ikea-mujoco/`. Plain MuJoCo 3.14.0 on the CPU (float64), two arms, physical grasps.

| item | robot | what is assembled | mechanism |
|---|---|---|---|
| `lack` | two Franka Panda | LACK side table: four legs screwed onto the top | threads (exact convex pieces), latched retention welds |
| `svallet` | ALOHA 2 | SVALLET lamp: the bulb screwed in, the shade snapped on | spring jaws and snaps, the bulb's thread |
| `gladom` | two Franka Panda | GLADOM tray table | threads (SDF meshes), latched welds |
| `variera` | two Franka Panda | VARIERA box: screws driven with a screwdriver | threads (SDF meshes) |
| `eket` | two Franka Panda | EKET cabinet: dowels and panels | latched retention welds |
| `ikea365` | two Franka Panda | IKEA 365+ stand and bowl: a screw driven with a screwdriver | threads (exact convex pieces), latched welds |
| `vesken` | two Franka Panda | VESKEN shelf unit: 23 snap connections | spring jaws and snaps |
| `stegesund` | two Franka Panda | STEGESUND stand: bolts driven with a hex key | capsule helices, seat welds |

- Each task has one reference for both modes, every row within the joint-speed limits (the privileged
  `solution/trajectory.npz` and the standard `solution/oracle_actions.npz` are the same rows). Each reference ends on
  the same state hashes on Intel AVX2, Intel AVX-512 and AMD Zen 4 hosts.
- The privileged row caps keep the verifier's replay within its time limit on a slow trial-class CPU (one reference
  replay on a Xeon Gold 6230R core, with a 1.5× margin). One reference replay takes from about 8 min (eket) to about 1 h 54 min (variera) on such a core;
  gladom and variera, whose SDF threads make MuJoCo's own step about 95 % of the time, are the slowest.
- The scene code is in git (`images/ikea-mujoco/scenes/<item>/`); the meshes are not, and every file's sha256 is pinned
  in `images/ikea-mujoco/assets.json`. A scene reads nothing from the environment (`rcb_ikea` drops the development
  switches `SW_FROM_OP` / `SW_FROM_T` on import). The image also holds four scenes that are not tasks.

## Others

- **Agent egress.** Every task's agent egress is the allowlist of `scripts/set_agent_egress.py` (model APIs and package
  registries).
- **Image builds.** `images/roboarc/README.md` (the puzzle image, built FROM `efe:robotangle-0.2.22` by digest) and
  `images/ikea-mujoco/README.md` (the IKEA images). A change to a file of `images/roboarc-files/FILES.json` needs a new
  files-image version (`scripts/files_image.py build roboarc-files`, push, `files_image.py pin`), then the tasks'
  `COPY --from` lines name the new digest.
