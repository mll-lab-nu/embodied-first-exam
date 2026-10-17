# vlabench-select-chemistry-tube-spatial-i00-standard

| | |
|---|---|
| Benchmark | VLABench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `vlabench-select-chemistry-tube-spatial-i00-privileged` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/select_chemistry_tube_spatial` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-vlabench:0.1.0` |

## Task
VLABench's `select_chemistry_tube_spatial` as a robot service: a Franka Panda arm at a table, instructed **"Take out the solution on the 1th row and 5th column"**
(a description of where the target is), on the same frozen instance as `vlabench-select-chemistry-tube-spatial-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a description of where the target is).

## Reference solution
`solution/`: the privileged oracle's 75 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the 9000-step technical cap, when the agent's
time is up, or on a simulator error) and writes that live verdict to `/data/final.json` (`graded_by = "live"`);
nothing is replayed to grade it (owner, 2026-10-17, board 0151). The scene is checked against the frozen instance (its
initial state and compiled model hashes) when it is built, and its start state when the episode begins (a mismatch is
`instance_mismatch`, infrastructure). `tests/grade.py` (separate sandbox, no network) grades `final.json`:
`success = live_success`. The video (`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and
never changes it.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 11 GB | 10 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim p90 6.9 GB, privileged container p90 8.1 GB, verifier 4.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 20 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 12 GiB (docker peak 7.2 GiB, 16 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | 9000 control steps (900 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Change Log
- 2026-10-16 (board 0136): the sim collect hook waits for the replay video until 2880 s after the episode ends (was 1470 s; `timeout_sec` 1500 -> 2910); the verdict keeps its 1440 s bound. The video replays the graded episode once more after the verdict, so a slow verdict left it no time. Video only: the verdict, the physics and the pass rule are unchanged, so results from before this date stay valid.
- 2026-10-17 (owner, board 0150/0151): graded by the live episode: `success` = VLABench's own success check reached in the episode the sim service ran (the same rule, judged as it ran), and no grading replay runs (no `replay_success` / `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json` `graded_by_live = 1`). The video is one render pass over the trajectory after the verdict, as before. The scene's start is checked when the episode begins: a scene that does not rebuild the frozen instance gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule, step cap and the agent's interface are unchanged, so the task keeps its name; archived verdicts are the same under the live rule, except 5 trials whose old video render ran out of time (recorded `infra_error`), which the live rule grades (all 0).
