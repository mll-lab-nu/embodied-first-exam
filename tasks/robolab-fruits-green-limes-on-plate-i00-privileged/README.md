# robolab-fruits-green-limes-on-plate-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-fruits-green-limes-on-plate-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `fruits_green_limes_on_plate` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-fruits-green-limes-on-pl__3NH9BN4 (robolab-fruits-green-limes-on-plate-i00-standard, run codex-gpt6_luna-xhigh, robolab-lunaxh-limited-0928, lab; https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/fruits_green_limes_on_plate/limited/). Human review per family (PROTOCOL §2.7). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robolab:0.1.2` |

## Task
Put all the green fruit on the plate.

## Difficulty
RoboLab labels this task "simple" (2 subtasks; attributes: color); its success term (`object_on_top`) asks for 2 objects onto clay_plates. The tooling gives only thin primitives (move_ee on Isaac Lab's differential IK, joint moves, gripper, hold), so every grasp, transport and placement is the agent's to build. RoboLab ships no expert solution.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-fruits-green-limes-on-pl__3NH9BN4` (standard mode, run `codex-gpt6_luna-xhigh`, batch `robolab-lunaxh-limited-0928`, host lab): [trial log](https://embodied-agent-interface-v2-internal.github.io/runs/robolab/codex-gpt6_luna-xhigh/fruits_green_limes_on_plate/limited/), [replay video](https://huggingface.co/datasets/eai-v2-internal/agent-runs/resolve/main/robolab/codex-gpt6_luna-xhigh/fruits_green_limes_on_plate/limited/replay.mp4)

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff RoboLab's
`success` term holds in every replay, the final-state hashes agree and the rebuilt frozen scene matches the recorded
one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The trajectory is the per-control-step (T, 8) action record;
with PhysX on the CPU a fresh process reproduces the live run bit for bit (the GPU pipeline does not, which is why
physics is pinned to the CPU); later replays inside one process can differ in the last bits, hence two fresh processes.
RoboLab's success term is instantaneous: it is checked after every control step and the first step where it holds ends
the episode (RoboLab's own termination; the replay stops there), so a goal state that holds at one control step counts.

No oracle; human review in PR #3 (PROTOCOL §2.7: per family, this task and its twin, a positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 13 GB | 13 GB |
| GPU memory | 6.5 GB | 6.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 4.0-5.5 GB per trial (one simulator), anon memory 7.6-10.3 GB, CPU p90 2.4-8 cores over 7 trials, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10); vram_profile peaks 14.5-15.7 GB include agents' extra simulator processes and Isaac's card-sized pools; author: one Isaac simulator per 32 GB of host RAM
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 24 GiB GPU memory, 24 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 24 GiB GPU memory, 24 GiB memory. Limits measured: GPU: 15.7 GiB on a 48 GB card, 15.3 on 24 GB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10); includes agents' extra simulators) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: the [environment] cap 24 GiB, which every past trial ran under (docker peak 23.4 GiB over 4 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Simulator | NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2 / Isaac Sim 5.1, PhysX on the CPU, RTX rendering), Franka Panda + Robotiq 2F-85 (DROID setup) |
| RoboLab task | `FruitsGreenLimesOnPlateTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (`scripts/task_cutoffs.toml`); out of it, every Python process pays ~2 min of Isaac Sim launch + scene build (docs/benchmarks/robolab.md) |
| Generator | `scripts/robolab/mk_tasks.py` (`scripts/robolab/families.json`, `template/privileged/`, `shared/`); docs/benchmarks/robolab.md |

### Change Log
- 2026-10-10: grading robustness and time limits; the scene, the frozen instance and the pass rule are
  unchanged, so the task keeps its name. `tests/grade.py`: each fresh-process replay has
  max(1800 s, 900 s + rows / 7.5) instead of a flat 1800 s and `[verifier] timeout_sec` is 29100 s (was 2400 s, less than two
  replays at their limit), so a long trajectory is graded instead of the verifier being killed; a replay that still runs
  out of time is `replay_timed_out` with `grader_error` = `infra_error` = 1; a file that is not a readable trajectory is
  `bad_trajectory` (was `grader_error`); `instance_ok` = 0 (the rebuilt scene differs on this host) sets `grader_error` and
  `infra_error`; every reward has `deterministic` and `infra_error`. Tooling: a failed replay video never voids the
  replay, and the video of a trajectory longer than 9,000 rows is a time lapse (at most 9,000 frames).
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The simulator image is `eai-robolab:0.1.2` (was 0.1.1): it holds the MDL materials and textures that RoboLab's asset library fetched from NVIDIA's Omniverse content bucket whenever a scene was built, so that the cameras show under the allowlist what they showed with open egress (on 0.1.1 without that download the table renders red). The scene, the frozen instance, the physics, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
- 2026-10-10 (board 0072): the agent's image no longer holds RoboLab's recorded example episode (`/opt/robolab/examples/recorded_data`: the actions of a successful `RubiksCubeAndBananaTask` run, a solution of `robolab-rubiks-cube-and-banana-i00-privileged` within the agent's reach, PROTOCOL §2.7); `environment/Dockerfile` removes it. Nothing at run time reads it (only RoboLab's `examples/run_recorded.py` does), so the scene, the frozen instance, the tooling and the pass rule are unchanged; a privileged trial from before this date could read that file.
