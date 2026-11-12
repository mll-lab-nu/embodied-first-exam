# abc-sim-sweep-i00-standard

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `abc-sim-sweep-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `sweep` / seed 0 (allowed seeds: [0, 11, 12]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.2.0` |

## Task
ABC Sim `sweep_away_paper_scraps_from_table` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Get the paper scraps into the trash can: sweep them into the dustpan with the brush and empty it into the can, or any other way. Success: all 2 scraps are inside the trash can at the same time (each scrap's centre within the can's inner radius of its axis and between its floor and its rim). Pushing scraps off the table does not count. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
2 crumpled paper scraps lie on the table, with a brush, a dustpan and a trash can (all loose objects). The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. Tool use with two hands: brush and dustpan, light scraps that slide and roll, and an emptying motion into a can. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 1288 rows, streamed as `joint_position` chunks through the client (`solution/oracle_stream.py`); the service executes exactly those rows and ends at the same state as the privileged replay.

## Verification
The live episode's verdict (PROTOCOL H.4): the sim sidecar judges the episode it ran by the task's rule (the 1.02 s hold included) and the collect hook (`/opt/abc-tools/standard/finalize.sh`) writes it to `final.json`; the verifier (the shared `v2_1/grade.py`) transcribes it. Nothing is replayed to grade it; the video is rendered from the trajectory afterwards. `nop`: the episode times out, reward 0.

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
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `acdf58bdd8888ca2`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `sweep_away_paper_scraps_from_table` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.
