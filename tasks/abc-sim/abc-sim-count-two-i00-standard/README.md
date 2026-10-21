# abc-sim-count-two-i00-standard

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `abc-sim-count-two-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `count_two` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` |

## Task
ABC Sim `count_two_into_opaque_box` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Follow the directive **"put exactly 2 objects in the box"**. Success: the box holds exactly 2 objects (of any kind). An object is in the box when its centre is inside the box's interior (between its walls, below the lid); the count is read anew at every step, so taking an object out again, or dropping in one too many, undoes it. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
Twelve small objects -- cubes, spheres, cylinders and triangular prisms in six colours (red, orange, yellow, green, blue, purple), small and large -- lie on the table next to an opaque box. The box's lid has a slot covered by a light spring-hinged flap: objects go in through the slot. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: medium. Grounding a counting directive in what the cameras show, and dropping small objects through a narrow slot covered by a flap into a box whose contents can no longer be seen. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 291 rows, streamed as `joint_position` chunks through the client (`solution/oracle_stream.py`); the service executes exactly those rows and ends at the same state as the privileged replay.

## Verification
The live episode's verdict (PROTOCOL H.4): the sim sidecar judges the episode it ran by the task's rule (the 1.02 s hold included) and the collect hook (`/opt/abc-tools/standard/finalize.sh`) writes it to `final.json`; the verifier (the shared `v2_1/grade.py`) transcribes it. Nothing is replayed to grade it; the video is rendered from the trajectory afterwards. `nop`: the episode times out, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 4 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: oracle trials of all 60 directories, RTX 4090 workstation, 2026-10-21 (docker stats every 3 s; the rcb_monitor's NVML samples): the sim sidecar 2.1 GB and 0.83 GiB of GPU memory (standard, chess; realtime 0.8 GB and 0.72 GiB), the agent's container (the client) 0.03 GB; the collect hook renders the video inside the sidecar (EGL)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 16 GiB memory. Limits measured: the agent's container holds Python and the client only (0.03 GB in the oracle trials, no GPU); the whole trial adds the sim sidecar (2.1 GB and 0.83 GiB of GPU memory at most in the oracle trials, 2026-10-21) under its 10 GiB cap; processes 512 and disk 20 GiB: design defaults.

## Details
| | |
|---|---|
| Upstream | ABC Sim, `abc_sim` of github.com/amazon-far/abc @ d0832d1 (Apache-2.0; assets CC BY 4.0 / MIT), on MuJoCo 3.6.0 |
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `5099066e29874d64`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `count_two_into_opaque_box` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.

### Change Log
- 2026-10-21: first version.
