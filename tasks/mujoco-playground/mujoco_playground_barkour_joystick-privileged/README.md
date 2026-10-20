# mujoco_playground_barkour_joystick-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_barkour_joystick-standard` |
| Simulator / robot | `mujoco` / `google-barkour-vb` |
| Family / instance | `mujoco_playground/BarkourJoystick` / seed 2 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `BarkourJoystick` (Google Barkour vB), rebuilt in plain MuJoCo from Playground's scene files: Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.
For 10 s the robot gets a joystick command schedule (2 segments: planar velocity and yaw rate in its own frame) and must track it without falling over. Its torso is pushed 12 times. The deliverable is one replayable trajectory of joint position targets
(`/app/output/trajectory.npz`, `(T, 12)`, T = 1000 (the whole schedule)).

## Difficulty
Velocity tracking for 10 s: the agent has to make a 12-joint quadruped walk (a gait, not one motion) and steer it through the schedule's changes of speed, direction and turning rate, and an open-loop trajectory of 1000 steps only works if it is computed against the simulator. Random pushes on the torso come at fixed but unannounced times; the gait has to absorb them without a joint leaving its box.

## Reference solution
A policy trained here on Playground's BarkourJoystick reward, pushes included (PPO on the CPU; the training code is not in the image), its targets recorded: worst segment errors 0.033 m/s and 0.028 rad/s. Replayed by `solution/solve.sh` (`solution/oracle.npy`, 1000 rows); the rows are float32-exact, so the
standard twin's client executes the same targets. Re-verified: two
fresh-process replays succeed and end in the same state.

## Verification
`tests/grade.py` in a separate sandbox without network: two replays, each in a fresh process, from the verifier's own
copy of the instance (`tests/instance.json`; the start state is checked against its hash on every load); pass iff both
succeed and end in the same state (`deterministic`). Oracle: success, worst segment errors 0.033 m/s and 0.028 rad/s. `nop`: no trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: GPU 1.0-1.3 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.6 GB, sim 0.7 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU p90 1.9 cores, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 cloud GPU hosts + an RTX 4090 workstation, 10-10)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: the [environment] cap 8 GiB, which every past trial ran under (docker peak 4.8 GiB over 9 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `menagerie/google_barkour_vb/scene_mjx.xml`; MuJoCo Menagerie @ 1b86ece (`google_barkour_vb`); simulated in MuJoCo 3.3.7 on the CPU |
| Instance | Playground's `reset` with `jax.random.PRNGKey(2)` and Playground's command process over the 1000 steps (and its pushes); chosen (seed 2; skipped 0: pushes null or weak (peak under 20% of the torso's weight; a 1-step kick is zero in Playground's half-sine); 1: pushes null or weak (peak under 20% of the torso's weight; a 1-step kick is zero in Playground's half-sine)) |
| Actions | 12 joint position targets per control step (0.01 s of simulated time); kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the actuators' own damping of 0.5 N m s/rad |
| Resources | 4 CPUs, no GPU (CPU physics, EGL or OSMesa rendering) |

### Change Log
- 2026-10-14 (review, B1-m2): `tests/grade.py` only. A replay process that died or ran out of time, a
  rebuilt start that does not match the instance's hash (`instance_mismatch`) and an exception of the verifier itself
  now write `infra_error = 1` beside `grader_error = 1`: no verdict on the agent. Before, they wrote `grader_error = 1`
  alone, which counted as the agent's 0. Every `reward.json` now carries `infra_error`. The scene, the instance, the
  pass rule and the reference are unchanged, so the task keeps its name; a past 0 with `grader_error = 1` was an
  infrastructure failure.
