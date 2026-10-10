# molmospaces-pick-and-place-next-to-i00-privileged

| | |
|---|---|
| Benchmark | MolmoSpaces |
| Mode | privileged |
| Twin | `molmospaces-pick-and-place-next-to-i00-standard` |
| Simulator / robot | `molmospaces` / `franka-robotiq-2f85` |
| Family / instance | `pick-and-place-next-to` |
| Oracle | `none` — no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1 by the separate verifier: molmospaces-pick-and-place-next__g7CLYbk (run codex-gpt6_luna-medium, batch molmospaces-luna-1006c; https://embodied-agent-interface-v2-internal.github.io/runs/molmospaces/codex-gpt6_luna-medium-openrouter/pick_and_place_next_to/unlimited/); human review in PR #47 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` |

## Task
Pick up the red tdk vhs tape and place it next to the soap bottle. One frozen episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-objaverse/FrankaPickandPlaceNextToHardBench/FrankaPickandPlaceNextToHardBench_20260305_json_benchmark`, episode 89:
an Objaverse object), with a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup). Privileged mode: full simulator state, unlimited resets; the deliverable is one
open-loop trajectory of joint-position targets, one row per control step.

## Difficulty
Pick a named object and put it down beside a named reference object, on the same surface and with at most a few centimetres between their bounding boxes, without moving the reference object much. The object starts with at least five other objects within 30 cm of it. 455 control steps (30 s).

## Reference solution
None is shipped. Upstream's scripted experts (`molmo_spaces/policy/solvers`) are reference solutions and are not in the
image; neither are grasp files nor the public MolmoBot trajectories (agent egress: the model APIs only).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes (`tests/grade.py`).
Each replay is upstream's evaluation loop: one upstream `Task.step` per row until upstream's `is_done()` (the
benchmark's 30 s horizon = 455 control steps) or the last row, then upstream's `judge_success()`
on the final state: the horizontal gap between the two objects' axis-aligned bounding boxes is between 0 and 6 cm; both rest on the same supporting body; and the reference object has moved at most 15 cm and rotated at most 60 degrees from its start pose. Pass iff both replays succeed and end in the same state; `replay.mp4` is rendered after
the verdict. No oracle; human review in PR #47 (PROTOCOL §2.7: per family, this task and its twin, a
positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 6 GB | 4 GB |
| GPU memory | 3.5 GB | 3.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).
- Measured: GPU 2.7 GB on L40S, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory and CPU author estimate (MuJoCo, CPU physics, EGL rendering)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 7 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 2.7 GiB on a 48 GB card (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)); one trial on a 24 GB card peaked at 18.4 GiB and would exceed: calibrate -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (no samples); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | molmo-spaces 0.2.9 (MuJoCo 3.5.0, CPU physics; EGL rendering on the GPU), benchmark `molmospaces-bench-v2/20260415`, package `procthor-objaverse/FrankaPickandPlaceNextToHardBench/FrankaPickandPlaceNextToHardBench_20260305_json_benchmark` (PnP-next-to-v2 (MolmoBot benchmarks)), episode 89, house procthor-objaverse val 1912 |
| Frozen episode | `environment/instance.json`: the upstream episode unchanged except `source` (its expert trajectory's path) removed, plus the numbers the texts quote (`facts`) and its t = 0 record (`t0`: state hash, action layout) |
| Generator | `scripts/molmospaces/mk_tasks.py` (`families.json`, `instances/`, `template/`, `shared/`); docs/benchmarks/molmospaces.md |

### Change Log
- 2026-10-10: how a file that is not a trajectory is recorded; the frozen episode, upstream's success rule and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: a file that cannot be read as a trajectory (not an npz, a pickled or non-numeric `actions`) is `bad_trajectory = 1` (was `grader_error = 1`; 0 either way), and every reward that ends early also carries `deterministic`. A pass before this change is a pass after it.
- 2026-10-10 (review round 2, board 0067): `tests/grade.py` writes `infra_error` = 1 next to every `grader_error` = 1 (a replay process that died or ran out of time, a frozen instance the host did not rebuild, an exception in the grader), as the other benchmarks do: a reader of `infra_error` alone (PROTOCOL §2.6) took these for the agent's 0. The reward is 0 in these cases, as before; the pass rule is unchanged, so the task keeps its name.
