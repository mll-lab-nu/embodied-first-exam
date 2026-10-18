# roboarc-blanket-flatten-04-i01-privileged

| | |
|---|---|
| Benchmark | RoboARC |
| Mode | privileged |
| Twin | `roboarc-blanket-flatten-04-i01-standard` |
| Simulator / robot | `roboarc` / `aloha-2` |
| Family / instance | `blanket_flatten` / seed 0 |
| Oracle | `full` |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-roboarc:0.2.0` |

## Task
RoboARC blanket_flatten (ALOHA 2, MuJoCo): produce one replayable trajectory. Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw. Frozen scene instance (variation easy, seed 0).

## Difficulty
Two 6-dof aloha (viperx) arms with parallel-jaw grippers on a fixed base with a 14-D joint-target action space at 40 Hz; success needs the task's predicate (above) held for 0.5 s. Grasping: assisted grasping (pbd_local_patch_v1).

## Reference solution
`solution/solve.sh` copies `solution/trajectory.npz` (sha256 `aea2c9fe88ec41e7…`) to `/app/output/`: the MuJoCo reference, which its author replayed to success with a reproducible end state outside Harbor. No Harbor oracle trial of it has been run yet, so no score is claimed here.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from the frozen instance (`/tests/instance.json`, staged from the image and checked against `tests/runtime_binding.json`) in a fresh process, twice; pass iff the
task's predicate holds after every replay (`tests/grade.py`). `/logs/verifier/replay.mp4` is rendered during the second
replay (two passes, no separate video replay). The physics (a deterministic GPU cloth step, the rest on the CPU) replays bit for bit on one host; the
final-state hashes (`deterministic`) are still diagnostic; the rebuilt frozen scene must match (`instance_ok`)
(robot_coding_bench's GPU-backend rule).
The replays are grading replays (tooling v19): if this family's episode has not ended after the last row, the
final targets are held for up to 2 s with the replay tolerances of the grader details; at least one replay must
reach the goal with the instance's own thresholds within the trajectory's rows.
A trajectory may have at most 37000 rows (`RCB_MAX_STEPS`: two replays must fit the verifier's timeout; a longer one is
`bad_trajectory`).

`nop` scored 0 on this base in both modes (the release image eai-roboarc 0.1.0; harbor run -a nop with rendering off (scripts/roboarc/harbor_check.py); 2026-10-14).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 2 |
| Memory | 10 GB | 5 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).
- Measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending; GPU 2 GB: owner 10-17, board 0150 (batch_eval_live trial peak 1.1 GB on 24 GB cards)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 20 GiB GPU memory, 24 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 20 GiB GPU memory, 24 GiB memory. Limits measured: partial MuJoCo measurements of 2026-10-13 (rendering off) with the protocol's margin; calibration pending.

## Details
| | |
|---|---|
| Grasping | assisted grasping (pbd_local_patch_v1) |
| Success rule | task-native success (goal_complete True; frozen parameters; terminal revision release_settling_v1) |

### Goal
Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw.

### Success requirements
- Cover at least 95% of the blanket's unfolded material area in top-down projection. Overlapping layers count only once, holes do not count, and a large outer bounding box is insufficient.
- The sheet must lie flat on the tabletop, fully in contact with the table surface: keep every cloth point at most 30 mm above the tabletop and no more than 8 mm below it.
- No material edge may stretch beyond 1.15 times its original length. Raised corners or pulling the blanket taut in the air do not count.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement from the start of confirmation at most 3 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

### Task failure conditions
- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

### Grader details (in addition to the requirements above)
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. Over the blanket the floor is the cloth's top: a target that would bring a gripper part other than its finger pads lower than the top of the cloth under it (less about one 1.5 mm layer) is stopped there too, so a gripper cannot crush the cloth into the table; the finger pads of a hand closing to pinch may reach about 6 mm into the cloth. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the safety readings report these stops as static_guard).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`s.safety()`, `s.status()["forcing"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a cloth particle faster than 20 m/s): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The blanket is 0.6 m x 0.48 m (0.288 m^2), so the coverage needs at least 0.2736 m^2 of its area in the top view. Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- Soft grasp patches: blanket: spatial radius 18 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 1.5, exposed patch required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- Grading: the verifier replays your trajectory twice in a fresh process. Its cloth step runs on the GPU on a deterministic solver and the rest on the CPU (MuJoCo, float64), so a replay reproduces your own run on the same host; the rule is kept as a margin: each replay runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in your own run can still complete; during that hold it accepts a blanket coverage of 92% instead of 95% and cloth speeds up to 80 mm/s instead of 30 mm/s (the displacement limit during the confirmation stays). Success needs both replays to succeed AND at least one of them to reach the goal with the thresholds above within your own rows (not only in the hold). Nothing else is relaxed: every other condition, the failure conditions and the confirmation time are the same. A recording stops at your own success, so a replay whose confirmation ends a few ticks later needs more rows: you may append copies of the final row (holding still) before saving. `s.replay(actions, grading=True)` replays as the verifier does.
- A failure is reported in `s.status()["episode_end"]` as "Cloth fell below the table" or "forced_breakdown: <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard stops against these limits.

### Provenance
- Frozen instance: a MuJoCo instance (`simulator.physics_engine` "mujoco", its scene frozen under `instance_assets/mujoco/`), built by TopoGym source `e2e2f564` (MuJoCo instance made before this image was built (TopoGym source e2e2f564; its bytes are bound into the release image eai-roboarc:0.2.0, scripts/robotangle/release_rebuild.py --instances)); bound to this release's runtime (source `c9171f79`, tooling `d8692e15`).
- Frozen instance files (`instance.json`, `instance_assets/`): not in this directory. They are in the private HF dataset `eai-v2-internal/robotangle-assets` at `cb43201c2832`, under `instances/blanket-flatten-04-i01/` (scripts/roboarc/assets.json pins each file's sha256). The image carries them, and `/opt/robotangle/stage_instance.py` copies this task's instance next to its `runtime_binding.json`, which names the instance's canonical sha256 and every asset's sha256. The tooling checks them again at every session start.
- Release: dev/robotangle_mujoco `7947eaa7b`, image `ghcr.io/mll-lab-nu/eai-roboarc:0.2.0` (images/roboarc/).
- Name: RoboARC is the published name of this benchmark (2026-10-13). Code identifiers keep the simulator's name: the simulator package `topogym`, the tooling `rcb_topogym.py`, `TOPOGYM_*` variables.

### Change Log
- 2026-10-14: new task of roboarc (RoboARC on MuJoCo 3.14.0, docs/benchmarks/roboarc.md): a new design of blanket_flatten: redesigned start states of the blanket, coverage 0.95. Its task files start from the Genesis 1.2.1 task `blanket-flatten-very-easy-i00` (privileged mode), with this design's own task text, rules and goal, its own frozen instance and its own reference.
- 2026-10-14: the grading rule (tests/grade.py; failure analysis 2026-10-14, item 12). Success needs both replays to succeed AND at least one of them to reach the goal with the instance's own thresholds within the trajectory's rows (`strict_replay_required` 1; `success_in_hold_only` 1 marks a trajectory whose replays succeeded only in the hold, not credited). From 2026-10-05 (R-hold) to this change a replay could also confirm within the hold, with its relaxed thresholds, and no strict goal was required: privileged mode has no graded live run, so the hold's thresholds were the effective goal. The frozen instance, the reference and the replay are unchanged; results graded before this change are re-graded from their recorded trajectories, nothing is re-run (scripts/roboarc/regrade.py). Runs: docs/benchmarks/roboarc.md (Grading replays).
