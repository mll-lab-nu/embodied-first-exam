# abc-sim-conveyor-pick-i00-realtime

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `abc-sim-conveyor-pick-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `conveyor_pick` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.2.0` |

## Task
ABC Sim `conveyor_pick` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Pick the three objects off the moving belt and put them in the bin. Success: all three objects' centres are inside the bin's interior (between its walls, below its rim) at the same time. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
A conveyor belt runs across the table in front of the arms, along y, between two rails; it carries three objects (canned food, bagged food, boxed drink) towards the left (+y) at about 9 cm/s. A bin stands right behind the belt (on its far side). The objects keep moving with the belt until they are lifted off it. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. The scene does not wait: the belt carries the objects past the arms, so each grasp has to be timed on a moving object, and the objects are of different shapes and sizes. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 274 rows, planned into the episode at the control steps where they ran in the privileged replay (`submit(..., at=step)`, sent ahead of the clock; `solution/oracle_plan.py`), so the service executes exactly those rows at S = 1.

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
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `73fd8e08bd4000ee`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `conveyor_pick` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.
