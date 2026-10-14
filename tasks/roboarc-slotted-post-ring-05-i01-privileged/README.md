# roboarc-slotted-post-ring-05-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-slotted-post-ring-05-i01-standard` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `slotted_post_ring` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-roboarc:0.1.0` |

## Task
RoboARC slotted_post_ring (ALOHA 2, MuJoCo): produce one replayable trajectory. Separate and place the entire removable metal ring inside the green dashed goal region. Keep the post, cord, beads and end discs on the puzzle/system side. Frozen scene instance (variation slotted_post_ring_hard_chain, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `9b6b921182119c26…`) to `/app/output/`: the MuJoCo reference, which its author replayed to success with a reproducible end state outside Harbor. No Harbor oracle trial of it has been run yet, so no score is claimed here.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the final-state hashes
(`deterministic`) are still diagnostic, as for the GPU families; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).
The replays are grading replays (tooling v19): if this family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; every replay may confirm
within that hold (R-hold, 2026-10-05). Whether one reached the goal with the instance's own thresholds within the
trajectory's rows is reported (`strict_goal_reached`), not required.
A trajectory may have at most 189000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (a release-candidate build of this benchmark's image (2026-10-13) that holds the same frozen instance; harbor run -a nop with rendering off (scripts/roboarc/harbor_check.py); 2026-10-13).

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
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision placement_region_v2_default_success) |

### Goal
Separate and place the entire removable metal ring inside the green dashed goal region. Keep the post, cord, beads and end discs on the puzzle/system side.

### Success requirements
- Put every part of the entire removable metal ring inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 221.812 mm above the tabletop.
- Keep the post, cord, beads and end discs, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 229.8 mm x 229.8 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes; for the cord every vertex of its links (capsules).
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The cord, beads and end discs are free to move (their speed is not checked), but no point of them may cross that plane.
- The cord is a chain of 87 rigid capsule links (16.47 mm long, 7 mm thick) on ball joints that bend and twist freely (no spring), with damping. The links do not deform: nothing about the cord's shape or volume ends the episode. A part of the chain (a link, bead, end disc or the ring) moving faster than 3 m/s or spinning faster than 120 rad/s is slowed by extra damping (a speed clamp); this is not reported and does not end the episode.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): slotted_chain: radius 76 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; the hold uses the thresholds above too (no tolerance for this family). Success needs both replays to succeed; each of them may complete its confirmation within that hold (whether one reached the goal with the thresholds above within your own rows is recorded, `strict_goal_reached`, not required). Nothing else changes. A recording stops at your own success, so a replay whose confirmation ends a few ticks later completes it in that hold; copies of the final row (holding still) appended before saving give it more room. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "connection_or_volume_invalid: <what>" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `eb4db660` (MuJoCo instance made before this image was built (TopoGym source eb4db660; its bytes are bound into the release image eai-roboarc:0.1.0, scripts/robotangle/release_rebuild.py --instances)); bound to this release's runtime (source `37aa7ac0`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `88e0136e1b97`, under `instances/slotted-post-ring-05-i01/` (scripts/roboarc/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `b842da320`, image `ghcr.io/mll-lab-nu/eai-roboarc:0.1.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-13: new task of roboarc (RoboARC on MuJoCo 3.14.0, docs/benchmarks/roboarc.md): a new design of slotted_post_ring: slotted #108 on a rigid capsule chain (hard). Its task files start from the Genesis 1.2.1 task `horseshoe-ring-hard-i00` (privileged mode), with this design's own task text, rules and goal, its own frozen instance and its own reference.
