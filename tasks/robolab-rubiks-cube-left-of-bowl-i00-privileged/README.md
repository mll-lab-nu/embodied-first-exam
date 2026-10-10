# robolab-rubiks-cube-left-of-bowl-i00-privileged

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | privileged |
| Twin | `robolab-rubiks-cube-left-of-bowl-i00-standard` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `rubiks_cube_left_of_bowl` / seed 0 |
| Oracle | `full` — The oracle scored 1 (deterministic, instance_exact) in Harbor runs robolab-rubiks-cube-left-of-bowl__onMcaQH (laptop, job tpl11-0927-1823-oracle-robolab-rubiks-cube-left-of-bowl-i00, at eaf2aff0) and robolab-rubiks-cube-left-of-bowl__tRHn5hq (ws3, job tpl19-0927-0430-oracle-robolab-rubiks-cube-left-of-bowl-i00, at fe045825), on a byte-identical tests/grade.py, frozen instance and oracle code (tests/test.sh differs only in the command that empties /logs/verifier before grading: rm -rf, the protocol v1.0 convention); the tooling (rcb_robolab.py) changed since only off the oracle and replay path: eaf2aff0 adds other families' registry entries; b3c7ca89 adds fail-safe 2.2 helpers and was re-checked through the same tooling path (the banana_in_bowl oracle trajectory ends in the same final state sha 61afa384566be3a5 with the old and the new CLI); cde31660 flips the depth default, which run-oracle and replay pass explicitly (depth=False); one docstring line now says standard mode. |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robolab:0.1.1` |

## Task
Put the rubiks cube to the left of the bowl.

## Difficulty
The second RoboLab task next to `robolab-banana-in-bowl-i00`, chosen to test something different: a **spatial relation** instead of containment. RoboLab's success term is `object_left_of(rubiks_cube, bowl, frame_of_reference="robot", require_gripper_detached=True)`: the horizontal vector from the bowl's pose to the cube's pose, in the robot's base frame, must lie within a 45 deg cone around the robot's +y axis, and the gripper must have let go. There is no distance limit and no support or level check. The scene (bowl, cube, banana on a different table from the banana task, top at z = 0.05 m) starts with the cube to the bowl's right, so the cube has to be carried across, past the bowl. The trap is the cube's reference point: the RoboLab asset puts the cube's origin on one of its faces, ~3 cm from its geometric centre (on the -y face at the reset pose), and both the success check and `s.objects()[...]["position"]` use that origin. A grasp aimed at `position` straddles the cube's edge: one finger lands on the cube's top, the descent stalls 2 cm high and the gripper cannot close (what the first oracle did, three times). The instructions of both modes state where the reference point is.

## Reference solution
`solution/oracle_rubiks_cube_left_of_bowl.py` (RoboLab ships no expert; written for this instance); `solution/solve.sh` records it into a
trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in two fresh processes; pass iff RoboLab's
`success` term holds in every replay, the final-state hashes agree and the rebuilt frozen scene matches the recorded
one (`tests/grade.py`), plus `/logs/verifier/replay.mp4`. The trajectory is the per-control-step (T, 8) action record;
with PhysX on the CPU a fresh process reproduces the live run bit for bit (the GPU pipeline does not, which is why
physics is pinned to the CPU); later replays inside one process can differ in the last bits, hence two fresh processes.
RoboLab's success term is instantaneous: it is checked after every control step and the first step where it holds ends
the episode (RoboLab's own termination; the replay stops there), so a goal state that holds at one control step counts.

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
| RoboLab task | `RubiksCubeLeftOfBowlTask`; the frozen instance (the full scene state after RoboLab's canonical seed-0 reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/robolab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | 5400 s in both modes: every Python process pays ~2 min of Isaac Sim launch + scene build (docs/benchmarks/robolab.md) |
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
