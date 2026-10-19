# yamlab-put-pot-on-cooktop-i04-privileged

| | |
|---|---|
| Benchmark | YAMLab |
| Mode | privileged |
| Twin | `yamlab-put-pot-on-cooktop-i04-standard` |
| Simulator / robot | `yamlab` / `i2rt-yam-bimanual` |
| Family / instance | `put_pot_on_cooktop` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:yamlab-0.1.0` |

## Task
Two I2RT YAM arms on a workstation table lift a pot together (both grippers must hold it) and put it down upright on a cooktop, then let go: YAMLab's PutPotOnCooktop. Instance i04: YAMLab's objects `pot` = `Pot/pot_004` and `cooktop` = `Cooktop/cooktop_004`, placed as in YAMLab teleoperation demonstration
`putpot_004.hdf5 demo_4` (its recorded initial state: both arms at the home pose, grippers open; placement-schedule entry 4: the pot at x = 0.711 m, y = 0.150 m, yaw -90°). The deliverable is one replayable
trajectory of YAMLab's own 14-D joint-position actions at 30 Hz (`/app/output/trajectory.npz`), graded by YAMLab's staged
success check with its evaluation thresholds.

## Difficulty
A two-arm lift: both grippers must hold the pot at once while it rises 5 cm, so the two grasps (one per handle or rim side) and the two arms' motions must be coordinated, and the pot must be carried and set down upright within 2 cm of its resting height on the cooktop, then released without knocking it over. Privileged mode gives every object's pose and size, the success check, unlimited resets and self-replay;
the primitives are only IK / joint moves and gripper commands. This mode is the control for the standard twin.

## Reference solution
`solution/oracle_actions.npy` (379 control steps, run by `solution/oracle.py` through the agent's own tooling): a
30-step (1 s) linear move from the home pose to the first action of the human teleoperation demonstration of this instance
(`putpot_004.hdf5 demo_4` of `yamlab/yamlab_datasets` @ `fc6be97`), then that demonstration's recorded actions, replayed open-loop.
YAMLab's demonstrations are not in the image, and the agent's network reaches only the model APIs and the package
registries.

## Verification
`tests/grade.py` in a separate sandbox: two replays, each in a fresh process, from the verifier's own copy of the instance
(`tests/instance.json`; the rebuilt start is checked against its hash); pass iff YAMLab's success check holds in both
(every stage latched) and both end in the same state (`deterministic`), plus `/logs/verifier/replay.mp4` (top camera and
both wrist cameras). Oracle: 379 control steps, every stage latched at the last one; the live run and two
fresh-process replays end in the same state (hash `25de7047553400f6`). `nop`: no trajectory, reward 0; no stage holds at
the start.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 4 |
| Memory | 16 GB | 9 GB |
| GPU memory | 5 GB | 5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 3.8-4.0 GB per trial, anon memory 11.1-11.8 GB, CPU p90 5.8-8.7 cores over 12 trials, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10); vram_profile peaks 5.5-6.5 GB on 24 GB cards; board 0048: about 11 GB RAM and 8 CPUs per simulator; verifier 7.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 16 GiB GPU memory, 24 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 24 GiB memory. Limits measured: GPU: 10.4 GiB on a 48 GB card, 6.5 on 24 GB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: the [environment] cap 24 GiB, which every past trial ran under (docker peak 16.0 GiB over 4 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | YAMLab @ ec0455d (MIT) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0; objects and demonstration from `yamlab/yamlab_datasets` @ fc6be97 (MIT) |
| YAMLab task | `PutPotOnCooktop-v0` with `is_evaluation_mode` (YAMLab's evaluation thresholds); the frozen instance (assets + full scene state + its hash) is `environment/instance.json` |
| Actions | 14 per control step (1/30 s): left joint1..6, left gripper, right joint1..6, right gripper; joints absolute targets (rad), gripper = `left_finger` target (m, -0.0475 open .. 0 closed) |
| Physics | PhysX on the CPU (sim dt 1/120 s, decimation 4), RTX rendering only when a frame is asked for |
| Image | built locally on every host (`images/yamlab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); out of it, every Python process pays ~1.5-2.5 min of Isaac Sim launch + scene build (docs/benchmarks/yamlab.md) |

### Provenance
Generated by `scripts/yamlab/mk_tasks.py` from `scripts/yamlab/instances.json` and `scripts/yamlab/frozen/put_pot_on_cooktop-i04/`
(chosen and frozen by `scripts/yamlab/select_instances.py` in `ghcr.io/mll-lab-nu/efe-private:yamlab-0.1.0`).

### Change Log
- 2026-10-10: grading robustness and time limits; the scene, the frozen instance and the pass rule are
  unchanged, so the task keeps its name. `tests/grade.py`: each fresh-process replay has
  max(1800 s, 1200 s + rows / 20) instead of a flat 1800 s and `[verifier] timeout_sec` is 13000 s (was 2400 s, less than two
  replays at their limit), so a long trajectory is graded instead of the verifier being killed; a replay that still runs
  out of time is `replay_timed_out` with `grader_error` = `infra_error` = 1; a file that is not a readable trajectory is
  `bad_trajectory` (was `grader_error`); `instance_ok` = 0 (the rebuilt scene differs on this host) sets `grader_error` and
  `infra_error`; every reward has `deterministic` and `infra_error`. Tooling: a failed replay video never voids the
  replay, and the video of a trajectory longer than 18,000 rows is a time lapse (at most 9,000 frames).
- 2026-10-10 (owner decision, board 0072): the frozen instance file no longer names the recording it was made from
  (`instance.json` had a `source` entry with the dataset, the file and the demonstration index, and the tooling's usage
  text named such a file; the reference solution replays that demonstration). Nothing reads the entry: the scene, its
  state hash, the tooling's behaviour and the pass rule are unchanged, so the task keeps its name.
