# behavior-turning-on-radio-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-turning-on-radio-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `turning_on_radio` / seed 301 |
| Oracle | `none` — No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: model trial behavior-turning-on-radio-i00__up5rnyp (behavior-lunaxh-t8-0927, privileged) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 version of this task (dev/qineng 912567fa; grader verdict and frozen instance unchanged since); agent log https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/turning_on_radio/unlimited/, verifier replay https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/turning_on_radio/unlimited/replay.mp4; not re-run on this version (static validation only). Human review per family (protocol §2.7). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Switch on the radio receiver that stands on the table in the living room.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- the radio receiver (`radio_receiver.n.01_1`) is switched on

## Difficulty
First-pass rating on the task-list site: easy. The 2026 challenge's 200 teleoperated demonstrations took 72 s on average (2,150 control steps at 30 Hz) and drove 5.7 m; the scene loads 4 rooms, and the goal uses `toggled_on`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts). Evidence that the task is solvable: model trial `behavior-turning-on-radio-i00__up5rnyp` (behavior-lunaxh-t8-0927), graded 1 by the separate verifier; its agent log is on the results site (https://embodied-agent-interface-v2-internal.github.io/runs/behavior-1k/codex-gpt6_luna-xhigh/turning_on_radio/unlimited/) and the verifier's replay on Hugging Face (https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/behavior-1k/codex-gpt6_luna-xhigh/turning_on_radio/unlimited/replay.mp4); `task.toml` `oracle_evidence` has the version it ran on.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes. A file the
grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen
instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).

No oracle: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on a positive example and a `nop` run per mode.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 6 |
| Memory | 16 GB | 16 GB |
| GPU memory | 10.5 GB | 10.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 9 GB with RCB_TEXTURE_BUDGET=0.1 (batch_eval_live vram override; live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10): 8.3-9.0 GB); CPU 6-9 cores per trial (board 0048, ps); author: 13-16 GB of RAM per Isaac process
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 24 GiB GPU memory, 24 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 24 GiB GPU memory, 24 GiB memory. Limits measured: GPU: 15.1 GiB held for most of the episode by the reference solution alone on a 48 GB card (L40S) with RCB_TEXTURE_BUDGET=0.1, the tasks' default (the tasks' own monitor, three oracle runs of two tasks on two hosts, 10-10: 15.14-15.15 GiB; the 9.0 GiB of the live sampler (nvidia-smi every 30 s, 13 AWS hosts + ws-1) was below that; uncapped trials reached 29.0 GiB on 48 GB cards, batch_eval_live vram_profile) -> max(1.5 x peak, peak + 4) rounded up to 24 (was 16: 5 % above the reference solution's own use); memory: the [environment] cap 24 GiB, which every past trial ran under (docker peak 23.8 GiB over 5 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_double_floor_lower`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | the agent's time (the `Agent time budget` row; the number lives in `scripts/task_cutoffs.toml`): every Python process pays ~3 min of Isaac Sim + scene load out of it; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
| Verifier time | each replay min(4 h, max(3600 s, 1200 s + steps / 2)); `[verifier] timeout_sec` 30600 s (two capped replays + 30 min) |

### Change Log
- 2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays min(4 h, max(3600 s, 1200 s + steps / 2)) instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s, so long trajectories hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its name; a trial graded before this date with `grader_error` = 1 can be regraded.
- 2026-10-09: a fall ends the episode as a failure (owner decision): once OmniGibson's own Falling rule (the base tilted more than 41.4° from upright, or more than 3 cm below the floor) has held for 10 s of simulated time, the tooling Session's episode ends (`status()['fallen']`; `s.reset()` starts again), and the verifier's replays end at the same control step (`reward.json` `fallen`). The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; a trajectory in which the robot falls over and stays down for 10 s scores 0, and results recorded before this change are reported separately.
- 2026-10-10: whose failure a 0 is (review of board 0067; the pass rule is unchanged). `tests/grade.py`: a file the agent wrote that cannot be graded (not an npz, object arrays, no `task` or `actions` entry) is `bad_trajectory` (was `grader_error`); a frozen scene that does not rebuild to the recorded one in the verifier (`instance_ok` 0) sets `infra_error` and `grader_error` (was a plain 0), and a replay that died or ran out of time sets `infra_error` next to `grader_error`; every `reward.json` carries `deterministic` and `infra_error`. The tooling's `replay` CLI skips an extra npz entry it cannot read and never lets its video recorder's start or stop decide a replay. The instruction states the runaway guard (200,000 control steps), the trajectory format and the grader's replay time limit. A trajectory that passed before still passes, so the task keeps its name.
- 2026-10-10 (2): the GPU-memory limit of the agent phase is 24 GiB (was 16 GiB). This is a change of the limit (`[metadata.resources.limits]`, the `## Resource limits` paragraph of `instruction.md`), not of the minimum the task declares: the reference solution alone holds 15.1 GiB for most of the episode on a 48 GB card with `RCB_TEXTURE_BUDGET=0.1` (three oracle runs, two tasks, two L40S hosts, the task's own monitor), which left 5 % under the old limit; the new one is max(1.5 x peak, peak + 4) rounded up, as for the other Isaac Sim benchmarks. Limits are still only recorded (enforcement is off), so no result changes; the scene, the pass rule and the verifier are unchanged, and the task keeps its name.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
