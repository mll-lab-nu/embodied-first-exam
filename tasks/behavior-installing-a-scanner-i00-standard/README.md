# behavior-installing-a-scanner-i00-standard

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `behavior-installing-a-scanner-i00-privileged` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `installing_a_scanner` / seed 301 |
| Oracle | `none` — No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: model trial behavior-installing-a-scanner-i0__pytvepD (behavior-lunaxh-t8-0927, the privileged twin behavior-installing-a-scanner-i00-privileged on the same frozen instance and BDDL goal) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 version of this task (dev/qineng 912567fa; grader verdict and frozen instance unchanged since); agent log https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/installing_a_scanner/unlimited/, verifier replay https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/installing_a_scanner/unlimited/replay.mp4; not re-run on this version (static validation only). Human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Standard-mode twin of `behavior-installing-a-scanner-i00-privileged` on the same frozen instance (2026 BEHAVIOR Challenge public_test instance 301): On the table in the private office stand a scanner (switched off) and a laptop; stand the scanner next to the laptop and switch the scanner on.

## Difficulty
Same scene, frozen instance and success rule as `behavior-installing-a-scanner-i00-privileged` (see its Difficulty). In standard mode the agent has no reset, no privileged state and no planning primitives: it sees the robot's cameras (RGB, depth on request) and its proprioception only, acts through the client, and gets one episode.

## Reference solution
None (`oracle = "none"`): no reference solution was written. Evidence that the task is solvable: the privileged twin's model trial `behavior-installing-a-scanner-i0__pytvepD` on the same frozen instance and BDDL goal (`task.toml` `oracle_evidence`).

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar;
`live_matches_replay` is reported separately, and so are the crash-recovery fields (`sim_startups`, `resumes`,
`resume_state_mismatch`, `infra_error`); `/logs/verifier/replay.mp4`.

No oracle: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on a positive example and a `nop` run per mode.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB-D + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (25, streamed at the 30 Hz control rate with the agent's `dt`; base entries are per-step targets) or of `ee_pose` (16, both end effectors, cuRobo IK per row); `observe` frames or a watch window; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service journals every control step (`journal.f64`) and resumes the same episode after a crash (resume class `approx`, docs/STANDARD_MODE_2_2.md §13.1); startup watchdog `RCB_STARTUP_TIMEOUT_S` = 1800 s |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Budget | 14400 s of agent wall clock, as the privileged twin (docs/benchmarks/behavior.md) |
| Collect hook time | 37800 s: the episode end (up to 2 h through a resume) + two replays of up to 4 h + 30 min |

### Sidecar and grading
The agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`: GPU on the sidecar, the licensed dataset mounted read-only at `/data`, the service's own
record in `/out`), which owns the scene and records the episode as a (T, 25) trajectory. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes
(Isaac: only the first replay in a process is bit-exact, and two simulators do not fit in one container) and writes
`final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

### Change Log
- 2026-10-08: collect-hook time limit only. `[[verifier.collect]] timeout_sec` is 37800 s (was 21600 s): the episode end (up to 2 h through a resume) plus two replays of up to 4 h each (the privileged grader's cap of min(4 h, max(3600 s, 1200 s + steps / 2))) plus 30 min; measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s. The replays still have no limit of their own. The scene, frozen instance and pass rule are unchanged, so the task keeps its name.
