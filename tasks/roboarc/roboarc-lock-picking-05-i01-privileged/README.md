# roboarc-lock-picking-05-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-lock-picking-05-i01-standard` |
| Simulator / robot | `roboarc` / `franka-robotiq-2f85` |
| Family / instance | `lock_picking` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` |

## Task
RoboARC lock_picking (Franka Panda + Robotiq 2F-85, MuJoCo): produce one replayable trajectory. Pick up the two-tab key from its rest. Insert the tabbed key through all four rotor plates and the final END plate, while respecting their slots and stops. The key's leading tab is longer than its second tab, which sits one plate spacing behind it. Frozen scene instance (variation lock_picking_hard, seed 0).

## Difficulty
A 7-dof franka panda arm with a robotiq 2f-85 parallel gripper on a fixed base with a 8-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (contact_weld_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `8bf6a0e983a3d152…`) to `/app/output/`: the MuJoCo reference (the released route re-recorded on MuJoCo with a held tail), which the verifier scored 1 in two fresh-process replays on the release image efe:roboarc-0.1.0 (2026-10-14; simulator source 37aa7ac0, tooling d8692e15).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics runs on the CPU and is bit-deterministic on one host; the
final-state hashes (`deterministic`) are still diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(Embodied First Exam's GPU-backend rule).
The replays are grading replays (tooling v18): if this family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; at least one replay must
reach the goal with the instance's own thresholds within the trajectory's rows.
A trajectory may have at most 200000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (the release image efe:roboarc-0.1.0; harbor run -a nop with rendering off (scripts/roboarc/harbor_check.py); 2026-10-14).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 2 |
| Memory | 7 GB | 5 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending; GPU 2 GB: owner 10-17, board 0150 (batch_eval_live trial peak 1.1 GB on 24 GB cards)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 12 GiB GPU memory, 24 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 12 GiB GPU memory, 24 GiB memory. Limits measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending.

## Details
| | |
|---|---|
| Grasping | assisted grasping (contact_weld_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision terminal_v6_chain_lock) |

### Goal
Pick up the two-tab key from its rest. Insert the tabbed key through all four rotor plates and the final END plate, while respecting their slots and stops. The key's leading tab is longer than its second tab, which sits one plate spacing behind it.

### Success requirements
- Keep the finite-length shaft passing through the full thickness of all five plates at once, facing the insertion direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all five bores. The radial numerical contact tolerance is 0.01 mm; do not push the shaft through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Sizes: bore radius 7.5 mm, shaft radius 6.75 mm. At each of the 10 plate faces (four 10 mm rotor plates and END, 120 mm apart), the shaft axis' distance from the bore axis plus 6.75 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm: about 0.76 mm of offset when the key is straight, which over the stack allows only about 0.18 degrees of tilt.
- The shaft reaches from 545 mm behind the leading tab to 15 mm in front of it; all 10 plate faces must lie within that length.
- Tabs: half-width 4 degrees; the leading tab reaches radius 36 mm and the second tab, 120 mm behind it, 22 mm. Slots: half-width 5.5 degrees, reaching radius 45 mm (deep) or 28 mm (shallow). A tab that overlaps a plate must sit inside one of that plate's slots that reaches beyond the tab, with an angular margin of at least asin(axis offset / tab radius) + the tilt.
- Rotor stops (from each rotor's start angle, seen from the side the key enters, looking along the key toward END; rotor 1 is the first plate the key reaches): rotor 1 2 degrees counterclockwise and 32 degrees clockwise; rotor 2 32 degrees counterclockwise and 2 degrees clockwise; rotor 3 2 degrees counterclockwise and 32 degrees clockwise; rotor 4 152 degrees counterclockwise and 2 degrees clockwise. Going more than 0.5 degrees beyond a stop ends the episode.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.
- Grading: the verifier replays your trajectory twice in a fresh process. This family's physics runs on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; the hold uses the thresholds above too (no tolerance for this family). Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else changes. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "rotor_limit_exceeded", "Key fell below table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `d1eb6f13` (MuJoCo instance made before this image was built (TopoGym source d1eb6f13; its bytes are bound into the release image efe:roboarc-0.2.0, scripts/robotangle/release_rebuild.py --instances)); bound to this release's runtime (source `c9171f79`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. The public image carries them in `/opt/robotangle/instances/lock-picking-05-i01/` (`images/roboarc/assets.json` pins each file's sha256), and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `7947eaa7b`, image `ghcr.io/mll-lab-nu/efe:roboarc-0.2.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-14: new task of roboarc (RoboARC on MuJoCo 3.14.0, tasks/roboarc/README.md): the scene, goal and rules of the Genesis 1.2.1 task `lock-picking-hard-i00` (privileged mode), ported to MuJoCo: its own frozen instance and reference, the numpy / OpenBLAS SIMD masking in every container that runs a Session, and the render bridge next to the tooling (Nyx frames).
- 2026-10-14: the grading rule (tests/grade.py; failure analysis 2026-10-14, item 12). Success needs both replays to succeed AND at least one of them to reach the goal with the instance's own thresholds within the trajectory's rows (`strict_replay_required` 1; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). From 2026-10-05 (R-hold) to this change a replay could also confirm within the hold, with its relaxed thresholds, and no strict goal was required: privileged mode has no graded live run, so the hold's thresholds were the effective goal. The frozen instance, the reference and the replay are unchanged; results graded before this change are re-graded from their recorded trajectories, nothing is re-run (scripts/roboarc/regrade.py). Runs: tasks/roboarc/README.md (Grading replays).
