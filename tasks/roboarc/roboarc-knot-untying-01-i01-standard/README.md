# roboarc-knot-untying-01-i01-standard

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | standard (`eai-standard/2.4`) |
| Twin | `roboarc-knot-untying-01-i01-privileged` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `knot_untying` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-roboarc:0.2.0` |

## Task
Standard-mode twin of `roboarc-knot-untying-01-i01-privileged` (same frozen instance): the agent gets only the `eai-standard/2.4` client
(docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory; its collect hook
(`environment/sim/finalize.sh`) writes the live episode's verdict, then renders the video in one video-only
replay of the recorded rows (no grading replay). The verifier runs in a separate sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and the tooling's primitives.

## Difficulty
Same scene, instance and success rule as `roboarc-knot-untying-01-i01-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/solve.sh` streams the recorded rows of the standard-mode oracle episode (`solution/oracle_qpos.npy`, one `joint_position` row per 25 ms control step, `hold`; the same rows as the privileged reference) through the client (`solution/oracle_replay.py`). That episode scored 1 (live and fresh replay) on a release-candidate build of this benchmark's image (2026-10-13) that holds the same frozen instance (2026-10-13; simulator source 7d0e5039, tooling 646f914f).

## Verification
See `tests/grade.py`.

`nop` scored 0 on this base in both modes (the release image eai-roboarc 0.1.0; harbor run -a nop with rendering off (scripts/roboarc/harbor_check.py); 2026-10-14).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 2 |
| Memory | 7 GB | 6 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending; GPU 2 GB: owner 10-17, board 0150 (batch_eval_live trial peak 1.1 GB on 24 GB cards)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 12 GiB GPU memory, 16 GiB memory. Limits measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending.

## Details

### Goal
Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it.

### Success requirements
- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope diameter plus 3 mm above it.
- Release all target parts and disengage any assisted grasp. Keep at least 1 mm of verified clearance between the rope and grippers or other robot links that can move. World-fixed bases may touch the rope normally. Interior overlap with any robot part is forbidden; ambiguous bounding-volume overlaps require a native-solid geometry check.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Grader details (in addition to the requirements above)
- The rope is a chain of 220 rigid capsule links (4.5 mm long, 8 mm thick) joined end to end; each joint bends and twists against a spring set by the rope's material, with damping, and stops bending at 0.9 rad, where neighbouring links touch. The links do not deform: nothing about the rope's shape or volume ends the episode. A link moving faster than 2 m/s or spinning faster than 150 rad/s is slowed by extra damping (a speed clamp); this is not reported and does not end the episode. Pulled harder than about 14.9 N, the rope's links get extra rotational inertia (a tension guard), which only removes energy and is not reported.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the response does not report these stops).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release check bounds the rope's volume mesh (carried rigidly by its capsule links), element by element, against the robot's collision geometries and decides the close ones with the exact solids: every robot part that can move (grippers, arm links) needs at least 1 mm of clearance from the rope; a world-fixed base may touch it. An overlap with the interior of any robot part means the release is not certified: no success while it lasts, never a failure.
- Grading: the live episode is the verdict: success needs it to succeed with the thresholds above (within its confirmation time); a live failure is final. Nothing is replayed to grade it: the video is rendered afterwards from the recorded rows and never changes the grade.

| | |
|---|---|
| mode | standard (RGB, optional depth, proprioception, calibrated cameras, no reset) |
| action space | `eai-standard/2.4`: `submit` chunks of `joint_position` (14, streamed at the 40 Hz control rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; binary RCB1 responses |
| oracle | `full` (`solution/`) |
| verification | `success` = the live success: the task predicate on the live simulator with the instance's own thresholds (its confirmation time included), as the sim service recorded it (`final.json`: `graded_by` live, `replays` 0); no grading replay (owner, 2026-10-17, board 0150/0151). The frozen instance is checked when the service builds it (`instance_mismatch`: infrastructure). After the verdict is written, one video-only fresh-process replay in the sidecar's collect hook renders `/logs/verifier/replay.mp4` (and, for a success held for review, the frames around its live review events); a failed video never changes the verdict |
| crash recovery | `eai-standard/2.4` §13: journal + per-call checkpoints, `restart: on-failure:6`, resume class `approx` |

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `d601866b` (MuJoCo instance made before this image was built (TopoGym source d601866b; its bytes are bound into the release image eai-roboarc:0.2.0, scripts/robotangle/release_rebuild.py --instances)); bound to this release's runtime (source `c9171f79`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `cb43201c2832`, under `instances/knot-untying-01-i01/` (scripts/roboarc/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `7947eaa7b`, image `ghcr.io/mll-lab-nu/eai-roboarc:0.2.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-14: new task of roboarc (RoboARC on MuJoCo 3.14.0, docs/benchmarks/roboarc.md): the scene, goal and rules of the Genesis 1.2.1 task `knot-untying-very-easy-i00` (standard mode), ported to MuJoCo: its own frozen instance and reference, the numpy / OpenBLAS SIMD masking in every container that runs a Session, and the render bridge next to the tooling (Nyx frames).
- 2026-10-17: roboarc 0.2.0: instruction.md drops the empty `## Task failure conditions` heading (no rule was left under it; instruction audit V6); the rules are unchanged.
- 2026-10-17 (owner, board 0150/0151): graded by the live episode; no grading replay. `success` = the live success (the instance's own thresholds; a live success with a deep task contact is still held for review); the fresh-process replay of the collect hook (with its grading hold and replay tolerances) no longer decides anything and runs only as the video-only pass after the verdict, so a replay failure, a GPU lost after the episode or a breakdown met only in the replay no longer voids a trial. The frozen instance, the rows and the agent's texts other than the grading line are unchanged.
