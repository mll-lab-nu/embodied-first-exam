# roboarc-interlocked-claws-04-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-interlocked-claws-04-i01-standard` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `interlocked_claws` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` |

## Task
RoboARC interlocked_claws (ALOHA 2, MuJoCo): produce one replayable trajectory. Completely separate the two claw pieces and briefly hold both still. Frozen scene instance (variation interlocked_claws_medium, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `d9ccaa4056d5ffa2…`) to `/app/output/`: the MuJoCo reference (the released route re-recorded on MuJoCo with a held tail), which the verifier scored 1 in two fresh-process replays on the release image efe:roboarc-0.1.0 (2026-10-14; simulator source 37aa7ac0, tooling d8692e15).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the final-state hashes
(`deterministic`) are still diagnostic, as for the GPU families; the rebuilt frozen scene must match (`instance_ok`)
(Embodied First Exam's GPU-backend rule).
A trajectory may have at most 200000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (the release image efe:roboarc-0.1.0; harbor run -a nop with rendering off; 2026-10-14).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 30 GiB | 8192 | 12 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 12 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision claws_separation_v1_grasp_contact_2mm) |

### Goal
Completely separate the two claw pieces and briefly hold both still.

### Success requirements
- Leave at least 10 mm between the complete pieces, with a plane separating all of their geometry; a gap inside the interlock is insufficient.
- Keep both pieces' linear speed at most 1 mm/s and angular speed at most 0.02 rad/s. Holding both pieces is allowed; release and transport into the green region are not required.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A task piece falling more than 100 mm below the tabletop ends the episode in failure. Contact penetration never ends the episode by itself: a success with a task contact deeper than 3 mm, or deeper than 2 mm for at least 0.25 s (100 consecutive physics ticks), is not credited automatically but reviewed, with the recorded evidence and frames (for a finger contact with a held movable piece: 4 mm, or 2 mm for 0.25 s; holding requires both fingers of the same hand to contact the same piece, or an active assisted grasp by that hand); a clean success is credited automatically. A task contact deeper than 10 mm is a simulator breakdown (Grader details).

### Grader details (in addition to the requirements above)
- Separation as the grader measures it: every vertex of both pieces' visual and collision meshes counts, and the gap is measured along ten directions only: the three world axes, each piece's own three body axes, and the line between the two pieces' centres (the mean of each piece's vertices). Along at least one of them the two pieces must be at least 10 mm apart; a separating plane in any other direction does not count. The green dashed square on the table is not part of this goal: neither containment in it nor a separator plane is checked.
- Contact penetration is read from the contacts at the end of every physics tick (2.5 ms; 10 ticks per control step). "Held" is decided anew at every tick: a zero-force touch counts, and if one finger loses contact (with no active assisted grasp), the other finger is back at the non-held limits in the same tick.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a non-finite state or a task contact deeper than 10 mm): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): piece_0: radius 30 mm; piece_1: radius 30 mm. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- A failure is reported in `s.status()["episode_end"]` as "A task body fell below the table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits, and `s.status()["review"]` the deep task contacts that would hold a success for review.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `d601866b` (MuJoCo instance made before this image was built (TopoGym source d601866b; its bytes are bound into the release image efe:roboarc-0.2.0)); bound to this release's runtime (source `c9171f79`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. The public image carries them in `/opt/robotangle/instances/interlocked-claws-04-i01/` (`images/roboarc/assets.json` pins each file's sha256), and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `7947eaa7b`, image `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark. Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.
