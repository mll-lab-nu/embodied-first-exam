# abc-sim-count-four-i00-privileged

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | privileged |
| Twin | `abc-sim-count-four-i00-standard` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `count_four` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` |

## Task
ABC Sim `count_four_into_opaque_box` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Follow the directive **"put exactly 4 objects in the box"**. Success: the box holds exactly 4 objects (of any kind). An object is in the box when its centre is inside the box's interior (between its walls, below the lid); the count is read anew at every step, so taking an object out again, or dropping in one too many, undoes it. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
Twelve small objects -- cubes, spheres, cylinders and triangular prisms in six colours (red, orange, yellow, green, blue, purple), small and large -- lie on the table next to an opaque box. The box's lid has a slot covered by a light spring-hinged flap: objects go in through the slot. The deliverable is one replayable trajectory (`/app/output/trajectory.npz`, `(T, 14)`, one row per 0.034 s control step).

## Difficulty
First-pass rating: hard. Grounding a counting directive in what the cameras show, and dropping small objects through a narrow slot covered by a flap into a box whose contents can no longer be seen. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The commanded actions of one of upstream's validation demonstrations of this task, replayed from the frozen instance and cut at the success step: `solution/oracle.npy`, 671 rows (float32 values, so the standard twin's client sends the same rows), success after the last one. Replayed, checked and saved by `solution/solve.sh`.

## Verification
`/opt/abc-tools/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in a fresh process (side by side), from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff both episodes end in success in the same state (`deterministic`). `nop`: no trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 5 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: oracle trials of all 60 directories, RTX 4090 workstation, 2026-10-21 (docker stats every 3 s; the rcb_monitor's NVML samples): the agent's container 1.9 GB (one Session replaying chess, no rendering), the verifier 3.9 GB (chess: two replays side by side, then the filmed one); a Session rendering three cameras 2.4 GB and 0.9 GiB of GPU memory (the spike, 2026-10-20); CPU 2.6-3.1 cores at peak
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 5 GiB GPU memory, 12 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 12 GiB memory. Limits measured: GPU: max(1.5 x 0.9, 0.9 + 4) GiB (a rendering Session 0.9 GiB); memory: several Sessions at once (2.4 GB each while rendering; the oracle trials' agent container 1.9 GB) under the 16 GiB cap by the monitor's margin; processes 512 and disk 10 GiB: design defaults.

## Details
| | |
|---|---|
| Upstream | ABC Sim, `abc_sim` of github.com/amazon-far/abc @ d0832d1 (Apache-2.0; assets CC BY 4.0 / MIT), on MuJoCo 3.6.0 |
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `c8a0c7b3eb8622b4`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `count_four_into_opaque_box` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.

### Change Log
- 2026-10-21: first version.
