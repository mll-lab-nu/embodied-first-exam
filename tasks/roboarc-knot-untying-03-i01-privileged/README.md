# roboarc-knot-untying-03-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-knot-untying-03-i01-standard` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `knot_untying` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-roboarc:0.1.0` |

## Task
RoboARC knot_untying (ALOHA 2, MuJoCo): produce one replayable trajectory. Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it. Frozen scene instance (variation knot_untying_easy, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: physical grasping only (no assisted grasping).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `366acc4f8e8a794c…`) to `/app/output/`: the MuJoCo reference (the released route re-recorded on MuJoCo with a held tail), which the verifier scored 1 in two fresh-process replays on the release image eai-roboarc 0.1.0 (2026-10-14; simulator source 37aa7ac0, tooling d8692e15).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the
final-state hashes (`deterministic`) are still diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).
The replays are grading replays (tooling v18): if this family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; at least one replay must
reach the goal with the instance's own thresholds within the trajectory's rows.
A trajectory may have at most 13000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (the release image eai-roboarc 0.1.0; harbor run -a nop with rendering off (scripts/roboarc/harbor_check.py); 2026-10-14).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 2 |
| Memory | 8 GB | 5 GB |
| GPU memory | 7 GB | 7 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 12 GiB GPU memory, 32 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 12 GiB GPU memory, 32 GiB memory. Limits measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending.

## Details
| | |
|---|---|
| Grasping | physical grasping only (no assisted grasping) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision terminal_v5_fixed_contact_active_clearance_1mm) |

### Goal
Untie and spread the rope on the tabletop until its top-down projection has no crossings or overlaps, then release it.

### Success requirements
- Remove projected crossings, overlaps, collapsed projected segments and exact foldbacks. Nonlocal rope segments must be separated by at least one rope diameter in the top-down view; merely changing over/under order is insufficient.
- Keep the entire rope close to the tabletop: no point more than 1 mm below it, and no point higher than one rope diameter plus 3 mm above it.
- Release all target parts and disengage any assisted grasp. Keep at least 1 mm of verified clearance between the rope and grippers or other robot links that can move. World-fixed bases may touch the rope normally. Interior overlap with any robot part is forbidden; ambiguous bounding-volume overlaps require a native-solid geometry check.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Grader details (in addition to the requirements above)
- The rope is a chain of 245 rigid capsule links (4.49 mm long, 8 mm thick) joined end to end; each joint bends and twists against a spring set by the rope's material (Young's modulus 50 kPa), with damping, and stops bending at 0.9 rad, where neighbouring links touch. The links do not deform: nothing about the rope's shape or volume ends the episode. A link moving faster than 2 m/s or spinning faster than 150 rad/s is slowed by extra damping (a speed clamp); this is not reported and does not end the episode. Pulled harder than about 15 N, the rope's links get extra rotational inertia (a tension guard), which only removes energy and is not reported.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The rope is 8 mm thick (radius 4 mm), so its highest point may be at most 11 mm above the tabletop.
- "Nonlocal" means at least 16 mm apart along the rope: such parts of the rope's centreline must be at least 8 mm apart in the top view. Closer parts are exempt, but an actual crossing always counts.
- The release check bounds the rope's volume mesh (carried rigidly by its capsule links), element by element, against the robot's collision geometries and decides the close ones with the exact solids: every robot part that can move (grippers, arm links) needs at least 1 mm of clearance from the rope; a world-fixed base may touch it. An overlap with the interior of any robot part means the release is not certified: no success while it lasts, never a failure.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; during that hold it accepts rope speeds up to 1.25 mm/s instead of 1 mm/s. Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else is relaxed: every other condition, the failure conditions and the confirmation time are the same. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `d601866b` (MuJoCo instance made before this image was built (TopoGym source d601866b; its bytes are bound into the release image eai-roboarc:0.1.0, scripts/robotangle/release_rebuild.py --instances)); bound to this release's runtime (source `37aa7ac0`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `88e0136e1b97`, under `instances/knot-untying-03-i01/` (scripts/roboarc/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `b842da320`, image `ghcr.io/mll-lab-nu/eai-roboarc:0.1.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-14: new task of roboarc (RoboARC on MuJoCo 3.14.0, docs/benchmarks/roboarc.md): the scene, goal and rules of the Genesis 1.2.1 task `knot-untying-easy-i00` (privileged mode), ported to MuJoCo: its own frozen instance and reference, the numpy / OpenBLAS SIMD masking in every container that runs a Session, and the render bridge next to the tooling (Nyx frames).
- 2026-10-14: the grading rule (tests/grade.py; failure analysis 2026-10-14, item 12). Success needs both replays to succeed AND at least one of them to reach the goal with the instance's own thresholds within the trajectory's rows (`strict_replay_required` 1; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). From 2026-10-05 (R-hold) to this change a replay could also confirm within the hold, with its relaxed thresholds, and no strict goal was required: privileged mode has no graded live run, so the hold's thresholds were the effective goal. The frozen instance, the reference and the replay are unchanged; results graded before this change are re-graded from their recorded trajectories, nothing is re-run (scripts/roboarc/regrade.py). Runs: docs/benchmarks/roboarc.md (Grading replays).
