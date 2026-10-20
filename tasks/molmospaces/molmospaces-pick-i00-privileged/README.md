# molmospaces-pick-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-pick-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-pick-i00-privileged__Y6SSCTZ (run codex-gpt6_1_sol-high, batch molmo-v2-sol, 2026-10-16); human review in PR #276 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5` |

## Task
Pick up the pie. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-objaverse/FrankaPickHardBench/FrankaPickHardBench_20260206_json_benchmark`, episode 806:
an Objaverse object), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Grasp and lift one named object in an unseen, cluttered house (ProcTHOR layout with Objaverse objects); the object must touch the robot and nothing else at the end, so a grasp that drops it, or still rests it on a surface, fails. The object starts with at least five other objects within 30 cm of it and shows small in the robot's fixed cameras (at most 1200 pixels in the best of them at t = 0). 303 control steps (20 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs and the package
registries; the PyPI distribution `molmo-spaces` has those experts, PROTOCOL §2.11).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 20 s horizon = 303 control steps) or the last row, then upstream's `judge_success()`
on the final state: the object touches the robot and nothing else, and it is at least 1 cm higher than where it started. Pass iff both replays succeed and end in the same state; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #276 (PROTOCOL §2.7: per family, this task and its twin, a
positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 6 GB | 4 GB |
| GPU memory | 3.5 GB | 3.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).
- Measured: GPU 2.7 GB on L40S, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory and CPU author estimate (MuJoCo, CPU physics, EGL rendering)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 7 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 2.7 GiB on a 48 GB card (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)); one trial on a 24 GB card peaked at 18.4 GiB and would exceed: calibrate -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (no samples); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickHardBench/FrankaPickHardBench_20260206_json_benchmark` (Pick-v2-classic (MolmoBot benchmarks)), episode 806, house procthor-objaverse val 4554 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Benchmark notes | tasks/molmospaces/README.md |

### Change Log
- 2026-10-10: how a file that is not a trajectory is recorded; the frozen episode, upstream's success rule and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: a file that cannot be read as a trajectory (not an npz, a pickled or non-numeric `actions`) is `bad_trajectory = 1` (was `grader_error = 1`; 0 either way), and every reward that ends early also carries `deterministic`. A pass before this change is a pass after it.
- 2026-10-10 (review round 2): `tests/grade.py` writes `infra_error` = 1 next to every `grader_error` = 1 (a replay process that died or ran out of time, a frozen instance the host did not rebuild, an exception in the grader), as the other benchmarks do: a reader of `infra_error` alone (PROTOCOL §2.6) took these for the agent's 0. The reward is 0 in these cases, as before; the pass rule is unchanged, so the task keeps its name.
- 2026-10-10 (review round 3): `tests/grade.py` only. A byte that is not valid UTF-8 in the session log the agent's tools write (`/app/output/rcb_session_log.jsonl`, read only for the self-reported `agent_*` cost fields) stopped the grader before it wrote a reward, so the trial had no verdict; the log is now read tolerantly and can no longer decide anything. A trial whose log is valid is graded as before; the pass rule is unchanged.
- 2026-10-16: the frozen episode, the base image and the replay limit. The frozen episode is the one the 2026-10-16 selection rule picks (tasks/molmospaces/README.md, Instances: the target small in the fixed cameras for the pick families, a longer travel for open and close); for every family but navigate-to and open-door that is a different episode, so results recorded on those tasks before this date are of another episode. Base image 0.2.5 (the assets of the new episodes). `tests/grade.py`: the two grading replays share the verifier's time (1740 s of its 1800 s; the first gets half of it) instead of 500 s each, which ended genuine successes on a loaded host as `replay_timed_out` + `infra_error`; the verdict, the pass rule and upstream's success rule are unchanged. `instruction.md` now states the pass rule (both replays succeed and end in the same state), which only this README stated.
