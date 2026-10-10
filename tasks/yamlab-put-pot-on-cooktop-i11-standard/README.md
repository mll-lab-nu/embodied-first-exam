# yamlab-put-pot-on-cooktop-i11-standard

| | |
|---|---|
| Benchmark | YAMLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `yamlab-put-pot-on-cooktop-i11-privileged` |
| Simulator / robot | `yamlab` / `i2rt-yam-bimanual` |
| Family / instance | `put_pot_on_cooktop` |
| Oracle | `full` |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-yamlab:0.1.0` |

## Task
Standard-mode twin of `yamlab-put-pot-on-cooktop-i11-privileged` (same frozen instance: YAMLab's objects `pot` = `Pot/pot_011` and `cooktop` = `Cooktop/cooktop_011` as placed in teleoperation
demonstration `putpot_011.hdf5 demo_2`, both arms at the home pose): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory of YAMLab's own actions. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes and
writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `yamlab-put-pot-on-cooktop-i11-privileged` (its README), without resets, object poses or the success signal: every step of a two-arm
manipulation is planned from three cameras (one static, two on the wrists), depth and the robot's own proprioception, and a
missed grasp or a dropped object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's actions (`solution/oracle_qpos.npy`: the 1 s ramp from the home
pose and the recorded teleoperation demonstration `putpot_011.hdf5 demo_2`, one row per control step, `hold`) as one-second
`joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the
control step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. YAMLab's success check (evaluation thresholds) is evaluated after
every control step; the episode ends at the first step where every stage has latched, live and in the replays. Oracle: the
live episode and both replays end in the privileged oracle's final state (hash `0eb70c669df35429`). `nop`: the episode ends
on the time-out with no stage reached, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 16 GB | 15 GB |
| GPU memory | 5 GB | 5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 3.8-4.0 GB per trial, anon memory 11.1-11.8 GB, CPU p90 5.8-8.7 cores over 12 trials, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + mll-4090-1, 10-10); vram_profile peaks 5.5-6.5 GB on 24 GB cards; board 0048: about 11 GB RAM and 8 CPUs per simulator; verifier 7.2 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10)

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step limit: it ends at the first control step where every stage of YAMLab's success check has latched, when a task object falls off the table, when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (14: YAMLab's own action, streamed at the 30 Hz control rate with the agent's `dt`, a multiple of 1/30 s) or `ee_pose` (16: both tool frames, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Cameras | `top` (static), `left_wrist`, `right_wrist` (on each arm's link_6), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs eai-yamlab (BUILD_ONLY, `images/yamlab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE_2_2.md §13) |
| Generator | `scripts/yamlab/mk_tasks.py` (`scripts/yamlab/instances.json`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/yamlab.md |
