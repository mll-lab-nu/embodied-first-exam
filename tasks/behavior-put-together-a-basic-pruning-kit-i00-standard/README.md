# behavior-put-together-a-basic-pruning-kit-i00-standard

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `behavior-put-together-a-basic-pruning-kit-i00-privileged` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `put_together_a_basic_pruning_kit` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (375 s on average); demonstration video (448 s): https://www.youtube.com/embed/UmGRVx-OCac (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Standard-mode twin of `behavior-put-together-a-basic-pruning-kit-i00-privileged` on the same frozen instance (2026 BEHAVIOR Challenge public_test instance 301): In the garage, put the pruner and the shears, which lie on the floor, inside the toolbox, which also stands on the floor, and close the toolbox; the toolbox stays on the floor.

## Difficulty
Same scene, frozen instance and success rule as `behavior-put-together-a-basic-pruning-kit-i00-privileged` (see its Difficulty). In standard mode the agent has no reset, no privileged state and no planning primitives: it sees the robot's cameras (RGB, depth on request) and its proprioception only, acts through the client, and gets one episode.

## Reference solution
None (`oracle = "none"`): no reference solution was written, and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's human teleoperation demonstrations of this activity on the R1Pro (`task.toml` `oracle_evidence`).

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar;
`live_matches_replay` is reported separately, and so are the crash-recovery fields (`sim_startups`, `resumes`,
`resume_state_mismatch`, `infra_error`); `/logs/verifier/replay.mp4`.

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB-D + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (25, streamed at the 30 Hz control rate with the agent's `dt`; base entries are per-step targets) or of `ee_pose` (16, both end effectors, cuRobo IK per row); `observe` frames or a watch window; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service journals every control step (`journal.f64`) and resumes the same episode after a crash (resume class `approx`, docs/STANDARD_MODE_2_2.md §13.1); startup watchdog `RCB_STARTUP_TIMEOUT_S` = 1800 s |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Budget | 14400 s of agent wall clock, as the privileged twin (docs/benchmarks/behavior.md) |

### Sidecar and grading
The agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`: GPU on the sidecar, the licensed dataset mounted read-only at `/data`, the service's own
record in `/out`), which owns the scene and records the episode as a (T, 25) trajectory. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes
(Isaac: only the first replay in a process is bit-exact, and two simulators do not fit in one container) and writes
`final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.
