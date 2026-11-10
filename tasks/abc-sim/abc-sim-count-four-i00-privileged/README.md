# abc-sim-count-four-i00-privileged

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | privileged |
| Twin | `abc-sim-count-four-i00-standard` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `count_four` / seed 0 (allowed seeds: [0, 88, 89]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.3.0` |

## Task
ABC Sim `count_four_into_opaque_box` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Follow the directive **"put exactly 4 objects in the box"**. Success: the box holds exactly 4 objects (of any kind). An object is in the box when its centre is inside the box's interior (between its walls, below the lid); the count is read anew at every step, so taking an object out again, or dropping in one too many, undoes it. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
Twelve small objects -- cubes, spheres, cylinders and triangular prisms in six colours (red, orange, yellow, green, blue, purple), small and large -- lie on the table next to an opaque box. The box's lid has a slot covered by a light spring-hinged flap: objects go in through the slot. The deliverable is one replayable trajectory (`/app/output/trajectory.npz`, `(T, 14)`, one row per 0.034 s control step).

## Difficulty
First-pass rating: hard. Grounding a counting directive in what the cameras show, and dropping small objects through a narrow slot covered by a flap into a box whose contents can no longer be seen. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The commanded actions of one of upstream's validation demonstrations of this task, replayed from the frozen instance and cut at the success step: `solution/oracle.npy`, 671 rows (float32 values, so the standard twin's client sends the same rows), success after the last one. Replayed, checked and saved by `solution/solve.sh`.

## Verification
`/opt/abc-tools/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff the episode ends in success. `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | 5 GiB | 10 GiB |
| verifier | 4 | 8 GiB | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

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
