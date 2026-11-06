# abc-sim-ball-tray-i00-realtime

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `abc-sim-ball-tray-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `ball_tray` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.2.0` |

## Task
ABC Sim `ball_tray_balancing` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Grab the tray by both handles -- the left gripper on one handle bar, the right gripper on the other -- and keep the ball on the tray. The moment both handle bars are touched by the fingers (one arm's fingers on each bar), an 11-second countdown starts and the ball gets a push every 0.5 s (a 0.1 s force in the tray's plane, up to ~0.18 m/s each, its direction drifting from push to push). Success: the countdown completes with the ball on the tray throughout and both handles held throughout (each bar touched by its arm's fingers within the last 0.1 s at every control step). Failure, which ends the episode: the ball leaves the tray (its centre outside the tray floor's central ~0.26 x 0.25 m area, or lower than 8 mm above the floor), or a handle is let go during the countdown.
A flat tray with a handle bar along each side lies on the table with a small ball on it. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. A bimanual grasp of both handles, then closed-loop balancing for 11 s against random pushes the agent cannot predict, with the ball's position known only from the cameras (standard modes). The action is joint-level (two 6-joint arms and two grippers; no motion primitives).

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 453 rows, planned into the episode at the control steps where they ran in the privileged replay (`submit(..., at=step)`, sent ahead of the clock; `solution/oracle_plan.py`), so the service executes exactly those rows at S = 1.

## Verification
The live episode's verdict, judged by the sim sidecar (the shared realtime layer and this benchmark's adapter) on the episode it ran; the collect hook waits for `final.json`; the verifier (the shared `v2_1/grade.py`) transcribes it. `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 10 GiB | 8192 | 5 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 20 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Upstream | ABC Sim, `abc_sim` of github.com/amazon-far/abc @ d0832d1 (Apache-2.0; assets CC BY 4.0 / MIT), on MuJoCo 3.6.0 |
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `6cdaa86a450092e7`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `ball_tray_balancing` held 30 control steps (ball tray: its own rule, tasks/abc-sim/README.md) |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.
