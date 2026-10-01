# robolab-banana-in-bowl-i00-standard

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robolab-banana-in-bowl-i00-privileged` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `banana_in_bowl` / seed 0 |
| Oracle | `partial` — solution/oracle_replay.py scored 1 in 6/6 recorded runs on the pre-crash-recovery service with the same verdict formula (success = live, replay and deterministic), the latest robolab-banana-in-bowl-i00-limit__vABaxSX (ws3, job eq-ws3-oracle-banana-in-bowl, 2026-09-29, the dev/qineng 9eb18edf version); not re-run on this version (crash recovery, the collect hook's `end`, one-second chunks): static validation only, 2026-10-01. Human review per family (PROTOCOL §2.7). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robolab:0.1.1` |

## Task
Standard-mode twin of `robolab-banana-in-bowl-i00-privileged` (same frozen instance, the state after RoboLab's canonical seed-0 reset):
the agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a (T, 8)
trajectory. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the
trajectory in two fresh processes (Isaac: only the first replay in a process is bit-exact, and two simulators do not fit
in one container) and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those
artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `robolab-banana-in-bowl-i00-privileged` (its README), without resets, object poses or the success predicate: every step is planned from camera images, depth and the robot's own proprioception, and a failed grasp or a knocked-over object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's joint targets (`oracle_qpos.npy`, one row per control step, `hold`) as one-second `joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the control step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. RoboLab's success term is instantaneous: it is checked after
every control step and the first step where it holds ends the episode (RoboLab's own termination), live and in the
replays.

Oracle `partial` (see Reference solution); human review in PR #3 (PROTOCOL §2.7: per family, this task and its twin, a positive example and the `nop` result).

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step limit: it ends at the first control step where RoboLab's success term holds, when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8, streamed at the 15 Hz control rate with the agent's `dt`, a multiple of 1/15 s) or `ee_pose` (8, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Images | the `sim` sidecar runs eai-robolab (BUILD_ONLY, `images/robolab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE_2_2.md §13) |
| Generator | `scripts/robolab/mk_tasks.py` (`scripts/robolab/families.json`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/robolab.md |
