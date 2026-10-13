# behavior-picking-up-trash-i00-privileged

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | privileged |
| Twin | `behavior-picking-up-trash-i00-standard` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `picking_up_trash` / seed 301 |
| Oracle | `partial` — Reference solution solution/oracle_picking_up_trash.py on the frozen task-level primitives solution/rcb_behavior_ref.py. Recorded Harbor oracle runs (laptop, pre-v1.0 uncommitted trees): 2026-09-24 behavior-picking-up-trash-i00__FKLU2nS (job behavior-picking-up-trash-i00-oracle-0924-230430) scored 1 (5115 control steps, deterministic 1, instance_exact 1); the run before it, behavior-picking-up-trash-i00__MjRvy7Y (an older placement routine), scored 0; the 2026-10-01 review counts 1 success in 3 runs of that version. Model trial behavior-picking-up-trash-i00__JRcB9fb (behavior-lunaxh-0925-2057, ws) scored 1. The tooling and verifier files changed since; not re-run on this version (static validation only). Measured 2026-10-10 on main 332bf8080 (board 0067 oracle sweep, AWS 8-vCPU L40S host rcb-gpu9, Harbor oracle agent, twice): the reference solution's own run put 2 of the 3 cans in (the third grasp closed on nothing; q_score 0.667, 4390 control steps), the verifier replayed it faithfully (deterministic 1) and scored 0; both runs were bit-identical. The frozen scene rebuilt there within tolerance but not bit-exactly (instance_exact 0), so the solution's online planning took another path than on the recording host: this reference solution does not succeed on that host class. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-behavior:0.1.1` |

## Task
Put the three cans of soda from the living room inside the trash can in the kitchen (BDDL: every `can__of__soda.n.01`
`inside` `ashcan.n.01_1`).

## Difficulty
Long-horizon mobile manipulation: three floor-level soda cans in the living room must be carried to a trash can in the
kitchen (~2.5 m navigation legs between rooms). The tooling gives only thin primitives (joint moves, a straight-line base
drive, cuRobo IK moves, gripper commands): navigation, grasping and placing are the agent's to build. What that takes,
from building the reference solution: the traversability map does not contain movable furniture (a 0.41 m cabinet blocks
the route between the rooms), the robot is a floating-base articulation that gets shoved around by any contact, IK near
the can in hand treats it as an obstacle unless told otherwise, the open fingers hang ~9 cm below the end-effector frame
and hook the rim when backing away, and the trash can is narrow at the bottom (fillable radius ~6.5 cm for 7.5 cm wide
cans) while the `inside` predicate tests each can's centre against a fillable volume that ends at z = 0.239 m, 4 cm below
the rim: a third upright can stacked on two others sticks out of it.

## Reference solution
`solution/oracle_picking_up_trash.py`: nearest can first; grasp (navigate → top-down pregrasp → descend → assisted
grasp), lift 0.6 m to carry above furniture, place it inside the trash can lying down (the pile stays low), reusing the
base pose of the first successful delivery. It runs on the task-level primitives of the tooling it was written with,
frozen in `solution/rcb_behavior_ref.py` (navigation on a map with the furniture painted in, grasp, `place_inside`);
`solution/solve.sh` records the trajectory with that copy (5115 control steps).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff the BDDL goal
holds after every replay, the final-state hashes agree and the rebuilt frozen instance matches the recorded one
(`tests/grade.py`), plus `/logs/verifier/replay.mp4`. A fresh process reproduces the live run bit for bit (the replay
starts from the loaded state, no reset); an in-process reset is only approximate, hence two fresh processes. A file the
grader cannot read or with the wrong shape is `bad_trajectory`; a replay that dies or runs out of time, and a frozen
instance that does not rebuild in the verifier (`instance_ok` 0), are `grader_error` + `infra_error` (no verdict on the agent).

Oracle `partial`: the reference solution scored 1 on earlier versions of this task (`task.toml` `oracle_evidence`) and was not re-run on this one; the family is reviewed by a maintainer (PROTOCOL §2.7) in the pull request that adds it.

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
