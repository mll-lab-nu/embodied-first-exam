# ambench-ndt-fahexa-i00-privileged

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | privileged |
| Twin | `ambench-ndt-fahexa-i00-standard` |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `ndt_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ambench-0.3.1` |

## Task
The hovering aerial manipulator starts outside a large warehouse building, facing one of its long walls, and high up on that wall a small rectangle is marked out with yellow-and-black hazard tape. Carry out a non-destructive-testing style inspection: bring the end effector to the fixed inspection point in front of the marked rectangle (see the goal geometry) and keep it there for 100 consecutive control steps (0.83 s). AM-Bench environment `NDT-Am-FAHexa-Abs-PID-Direct-v0` (the fully actuated hexarotor with the 4-joint arm, AM-Bench's PID
controller), its seeded reset with seed 0. The deliverable is one replayable trajectory of AM-Bench's absolute
end-effector pose actions at 120 Hz (`/app/output/trajectory.npz`), graded by AM-Bench's own success check within the
task's episode length of 20 s.

## Difficulty
The inspection point is several metres above the start, in front of a wall, and the end effector has to be kept inside a small region (6 cm deep, 16 cm across) for 100 consecutive steps from a hovering base. Privileged mode gives the full simulator state, unlimited resets and self-replay; the tooling offers only the
environment's own action, its state and its cameras.

## Reference solution
`solution/oracle_actions.npy` (run by `solution/oracle.py` through the agent's own tooling): AM-Bench's scripted expert
for this task, run on this instance (it reads the simulator's state in closed loop) and recorded, followed by 2 s of
holding its last command (a replay may succeed a step later than the live run; rows after success never run). The image
has no expert (`images/ambench/Dockerfile` removes them), and the agent's network reaches only the
model APIs and the package registries.

## Verification
`tests/grade.py` in a separate sandbox: up to 3 replays (`[metadata] replays`), each in a fresh process, stopping at the first success, from the verifier's own copy of the
instance (`tests/instance.json`; the rebuilt start is checked against its hash); pass iff AM-Bench's success check holds
in any of them (`replays_succeeded`; tasks/ambench/README.md, Determinism). `/logs/verifier/replay.mp4` (both onboard cameras) is filmed after the verdict
by the `film` CLI, the same rows drawn by the render worker, an illustration only. Oracle: success at control step
1212 (10.1 s simulated) in both fresh-process replays, which end in the frozen end state (hash
`bd8da2528c86e757`; a rare race can change the last bits of one, never measured to change the outcome). `nop`: no
trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 34 GiB | 1024 | 16 GiB | 10 GiB |
| verifier | 8 | 24 GiB | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, RTX 4090, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Upstream | AM-Bench @ 60bf5b7 (Apache-2.0) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0; Pyroki @ 2eafc99, acados @ fa0af20 |
| Instance | `NDT-Am-FAHexa-Abs-PID-Direct-v0`, seed 0, the start's state hash in `environment/instance.json` (`initial_sha` d3f1714e3cd2f6e6) |
| Actions | 8 per control step (1/120 s): end-effector target x y z (m), quaternion w x y z (command frame), gripper (-1 closed .. +1 open) |
| Physics | PhysX on the GPU (dt 1/120 s, one physics step per action), bit-reproducible in a fresh process; the onboard cameras (`Session(cameras=True)`) are drawn by a second, render-only Isaac process from the physics state |
| Image | built locally on every host (`images/ambench/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); out of it, every Python process pays ~2-6 min of Isaac Sim launch + scene build |

### Provenance
The frozen instance and the expert's rows were recorded in `ghcr.io/mll-lab-nu/efe-private:ambench-0.2.0`.
