# roboarc-slotted-post-ring-03-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-slotted-post-ring-03-i01-standard` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `slotted_post_ring` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` |

## Task
RoboARC slotted_post_ring (ALOHA 2, MuJoCo): produce one replayable trajectory. Separate and place the entire removable metal ring inside the green dashed goal region. Keep the post, cord, beads and end discs on the puzzle/system side. Frozen scene instance (variation slotted_post_ring_easy_chain, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `9fbd149690e0187d…`) to `/app/output/`: the MuJoCo reference (this design's oracle, recorded on MuJoCo), which the verifier scored 1 in two fresh-process replays on an earlier build of this benchmark's image (2026-10-13) that holds the same frozen instance (2026-10-13; simulator source d601866b, tooling fde662d5).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in one fresh process; pass iff the
task's predicate holds after the replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during that
replay (one pass, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; with one replay
no final-state hashes are compared (`determinism_checked` 0); the rebuilt frozen scene must match (`instance_ok`)
(Embodied First Exam's GPU-backend rule).
The replay is a grading replay (tooling v19): if this family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; the replay must
reach the goal with the instance's own thresholds within the trajectory's rows.
A trajectory may have at most 200000 rows (`RCB_MAX_STEPS`: the replay must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (the release image efe:roboarc-0.1.0; harbor run -a nop with rendering off; 2026-10-14).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 7 | 23 GiB | 1024 | 4 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 4 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision placement_region_v2_default_success) |

### Goal
Separate and place the entire removable metal ring inside the green dashed goal region. Keep the post, cord, beads and end discs on the puzzle/system side.

### Success requirements
- Put every part of the entire removable metal ring inside the fixed goal volume, leaving at least 1 mm inside its horizontal border. The centre alone is insufficient; no tip, spike, ring segment or cord segment may remain outside.
- Keep the target above the tabletop (contact tolerance 1 mm below the surface) and within the goal volume's height. It need not touch the table. The goal volume extends 230.257 mm above the tabletop.
- Keep the post, cord, beads and end discs, and every other remaining puzzle component, entirely on the system side of the fixed separator. Moving the whole puzzle into the goal is not completion.
- Keep each target rigid part's linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding the target with the gripper is allowed; release is not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Grader details (in addition to the requirements above)
- Goal square in this instance: the inner edge of the 2 mm wide dashed green line is the containment limit (the region's border runs along the middle of the line); it encloses a 238.3 mm x 238.3 mm square. Every point counts: for a rigid part every vertex of its visual and collision meshes; for the cord every vertex of its links (capsules).
- The separator is an invisible, fixed vertical plane parallel to the goal square's near edge, 5 mm beyond the point of all remaining components that was closest to the goal square at the start; the square's near edge is at least 30 mm beyond it. The cord, beads and end discs are free to move (their speed is not checked), but no point of them may cross that plane.
- The cord is a chain of 87 rigid capsule links (16.47 mm long, 7 mm thick) on ball joints that bend and twist freely (no spring), with damping. The links do not deform: nothing about the cord's shape or volume ends the episode. A part of the chain (a link, bead, end disc or the ring) moving faster than 3 m/s or spinning faster than 120 rad/s is slowed by extra damping (a speed clamp); this is not reported and does not end the episode.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a MuJoCo instability: a non-finite or diverging acceleration, position or velocity): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): slotted_chain: radius 79 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- Grading: the verifier replays your trajectory once in a fresh process. This family's physics runs on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: the replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; the hold uses the thresholds above too (no tolerance for this family). Success needs the replay to succeed AND to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else changes. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "connection_or_volume_invalid: <what>" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `d601866b` (MuJoCo instance made before this image was built (TopoGym source d601866b; its bytes are bound into the release image efe:roboarc-0.2.0)); bound to this release's runtime (source `c9171f79`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. The public image carries them in `/opt/robotangle/instances/slotted-post-ring-03-i01/` (`images/roboarc/assets.json` pins each file's sha256), and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `7947eaa7b`, image `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark. Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.
