# ambench-cabinet-pick-place-fahexa-i00-privileged

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | privileged |
| Twin | `ambench-cabinet-pick-place-fahexa-i00-standard` |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `cabinet_pick_place_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ambench-0.3.1` |

## Task
A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet: AM-Bench counts success when the can's centre is less than 5 cm above a fixed height just below the cabinet's top surface (there is no horizontal condition) while the can moves slower than 0.1 m/s. AM-Bench environment `CabinetPickPlace-Am-FAHexa-Abs-PID-Direct-v0` (the fully actuated hexarotor with the 4-joint arm, AM-Bench's PID
controller), its seeded reset with seed 0. The deliverable is one replayable trajectory of AM-Bench's absolute
end-effector pose actions at 120 Hz (`/app/output/trajectory.npz`), graded by AM-Bench's own success check within the
task's episode length of 60 s.

## Difficulty
The can is small (4 cm across, 5 g), enclosed in a shallow compartment behind a closed sliding door, and has to end up still at the height of the top of a tall cabinet, all from a hovering base. Privileged mode gives the full simulator state, unlimited resets and self-replay; the tooling offers only the
environment's own action, its state and its cameras.

## Reference solution
`solution/oracle_actions.npy` (run by `solution/oracle.py` through the agent's own tooling): AM-Bench's scripted expert
for this task, run on this instance (it reads the simulator's state in closed loop) and recorded, followed by 2 s of
holding its last command (a replay may succeed a step later than the live run; rows after success never run). The image
has no expert (`images/ambench/Dockerfile` removes them), and the agent's network reaches only the
model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: two replays, each in a fresh process, from the verifier's own copy of the
instance (`tests/instance.json`; the rebuilt start is checked against its hash); pass iff AM-Bench's success check holds
in both (`deterministic`: the outcome repeats; the end-state hashes are reported as `state_identical`, not decisive:
tasks/ambench/README.md, Determinism). `/logs/verifier/replay.mp4` (both onboard cameras) is filmed after the verdict
by the `film` CLI, the same rows drawn by the render worker, an illustration only. Oracle: success at control step
2752 (22.933 s simulated) in both fresh-process replays, which end in the frozen end state (hash
`c8c72a8b2031348e`; a rare race can change the last bits of one, never measured to change the outcome). `nop`: no
trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 4 |
| Memory | 16 GB | 16 GB |
| GPU memory | 8 GB | 8 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: freezing the instances, oracle trials and replays (RTX 4090, 2026-10-13/14, docker stats and nvidia-smi every 2-10 s, rcb_monitor): with one environment's PhysX buffers (the tooling's), a camera-free Isaac process (the default Session, the grader's replays) peaks at 2.0 GiB of memory and 1.2 GiB of GPU memory (Isaac Lab's default buffers: 2.9 / 3.2); the render worker that draws the cameras (Session(cameras=True), the verifier's filmed illustration) adds 11.9 GiB and 3.4 GiB (3.3-3.6 under every RTX preset tried); 6-10 cores while Isaac starts, about 1.5 after; the verifier runs one process at a time. The minimums cover one camera-on Session
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 16 GiB GPU memory, 28 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 28 GiB memory. Limits measured: a Session with cameras peaks at 14 GiB of memory and 4.6 GiB of GPU memory (its render worker included), a camera-free one at 2.0 / 1.2 (the rule's measurement); the agent may run two Sessions with cameras at once: at most 28 GiB, 9.2 GiB -> memory 28 GiB (the container's cap 34 GiB: 34 / 1.2 >= 28), GPU 16 GiB (at least 16 for Isaac Sim); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | AM-Bench @ 60bf5b7 (Apache-2.0) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0; Pyroki @ 2eafc99, acados @ fa0af20 |
| Instance | `CabinetPickPlace-Am-FAHexa-Abs-PID-Direct-v0`, seed 0, the start's state hash in `environment/instance.json` (`initial_sha` bd6848fff4488168) |
| Actions | 8 per control step (1/120 s): end-effector target x y z (m), quaternion w x y z (command frame), gripper (-1 closed .. +1 open) |
| Physics | PhysX on the GPU (dt 1/120 s, one physics step per action), bit-reproducible in a fresh process; the onboard cameras (`Session(cameras=True)`) are drawn by a second, render-only Isaac process from the physics state |
| Image | built locally on every host (`images/ambench/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); out of it, every Python process pays ~2-6 min of Isaac Sim launch + scene build |

### Provenance
The frozen instance and the expert's rows were recorded in `ghcr.io/mll-lab-nu/efe-private:ambench-0.2.0`.
