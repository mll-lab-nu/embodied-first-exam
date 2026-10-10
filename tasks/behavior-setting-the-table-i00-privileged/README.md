# behavior-setting-the-table-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-setting-the-table-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `setting_the_table` / seed 301 |
| Oracle | `none` — No reference solution and no verified positive example yet: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance, and no model trial has solved this task. Solvable by a human with this robot: the 2026 BEHAVIOR Challenge publishes 200 teleoperated demonstrations of this activity on the R1Pro in this scene model (594 s on average); demonstration video (727 s): https://www.youtube.com/embed/Tkf34ap-z8U (challenge task list https://behavior.stanford.edu/challenge/tasks/index.html). Supplementary task (added 2026-10-04); human review per family (protocol §2.7). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Set the dining-room breakfast table for two. The two plates are inside a kitchen cabinet, the two cupcakes inside the kitchen refrigerator, and two forks and two table knives lie on the kitchen sink. Put both plates on the breakfast table, one cupcake on each plate, and one fork and one knife next to each plate.

**Success**, all at the same time (the episode ends by itself the moment they hold):
- both plates (`plate.n.04_1`, `_2`) are on top of the breakfast table (`breakfast_table.n.01_1`)
- each cupcake (`cupcake.n.01_1`, `_2`) is on top of a different plate: one cupcake per plate
- each fork (`tablefork.n.01_1`, `_2`) is next to a different plate: one fork per plate
- each table knife (`table_knife.n.01_1`, `_2`) is next to a different plate: one knife per plate

## Difficulty
First-pass rating on the task-list site: extreme. The 2026 challenge's 200 teleoperated demonstrations took 594 s on average (17,808 control steps at 30 Hz) and drove 55.46 m; the scene loads 7 rooms, and the goal uses `nextto`, `ontop`.

## Reference solution
None (`oracle = "none"`): no reference solution was written (the challenge ships teleop demos, not scripts), and no positive example has been graded by this verifier yet. Evidence that the task is solvable: the 2026 BEHAVIOR Challenge's 200 human teleoperation demonstrations of this activity on the R1Pro (594 s on average; video https://www.youtube.com/embed/Tkf34ap-z8U); `task.toml` `oracle_evidence`.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes. A file the
grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen
instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).

No oracle and no verified positive example: the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it, on the official human demonstrations and a `nop` run per mode; until a positive example scores 1, its results are reported separately from the tasks with a verified solution (PROTOCOL §7, open item 4).

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
| Instance | 2026 BEHAVIOR Challenge public_test instance 301 (scene `house_single_floor`), state hash in `environment/instance.json` |
| Image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` = `stanfordvl/behavior:3.9.2` + ffmpeg; BUILD_ONLY, built on every host (`images/behavior/`) |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition), never baked in |
| GPU | an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`, `count: 1`) |
| Budget | 14400 s: every Python process pays ~3 min of Isaac Sim + scene load; ~7-11 control steps/s (docs/benchmarks/behavior.md) |
| Verifier time | each replay min(4 h, max(3600 s, 1200 s + steps / 2)); `[verifier] timeout_sec` 30600 s (two capped replays + 30 min) |

### Change Log
- 2026-10-08: verifier time limits only. `tests/grade.py` gives each of the two fresh-process replays min(4 h, max(3600 s, 1200 s + steps / 2)) instead of a flat 3600 s, and `[verifier] timeout_sec` is 30600 s (was 5400 s), measured on an 8-vCPU L40S host (job #3137): the Isaac start took 626 s and a 10,475-step replay ran slower than 3.5 control steps/s, so long trajectories hit the old limit as a grader error. The scene, frozen instance and pass rule are unchanged, so the task keeps its name; a trial graded before this date with `grader_error` = 1 can be regraded.
- 2026-10-09: a fall ends the episode as a failure (owner decision): once OmniGibson's own Falling rule (the base tilted more than 41.4° from upright, or more than 3 cm below the floor) has held for 10 s of simulated time, the tooling Session's episode ends (`status()['fallen']`; `s.reset()` starts again), and the verifier's replays end at the same control step (`reward.json` `fallen`). The scene, frozen instance and BDDL goal are unchanged, so the task keeps its name; a trajectory in which the robot falls over and stays down for 10 s scores 0, and results recorded before this change are reported separately.
- 2026-10-10: whose failure a 0 is (review of board 0067; the pass rule is unchanged). `tests/grade.py`: a file the agent wrote that cannot be graded (not an npz, object arrays, no `task` or `actions` entry) is `bad_trajectory` (was `grader_error`); a frozen scene that does not rebuild to the recorded one in the verifier (`instance_ok` 0) sets `infra_error` and `grader_error` (was a plain 0), and a replay that died or ran out of time sets `infra_error` next to `grader_error`; every `reward.json` carries `deterministic` and `infra_error`. The tooling's `replay` CLI skips an extra npz entry it cannot read and never lets its video recorder's start or stop decide a replay. The instruction states the runaway guard (200,000 control steps), the trajectory format and the grader's replay time limit. A trajectory that passed before still passes, so the task keeps its name.
- 2026-10-10 (2): the GPU-memory limit of the agent phase is 24 GiB (was 16 GiB). This is a change of the limit (`[metadata.resources.limits]`, the `## Resource limits` paragraph of `instruction.md`), not of the minimum the task declares: the reference solution alone holds 15.1 GiB for most of the episode on a 48 GB card with `RCB_TEXTURE_BUDGET=0.1` (three oracle runs, two tasks, two L40S hosts, the task's own monitor), which left 5 % under the old limit; the new one is max(1.5 x peak, peak + 4) rounded up, as for the other Isaac Sim benchmarks. Limits are still only recorded (enforcement is off), so no result changes; the scene, the pass rule and the verifier are unchanged, and the task keeps its name.
