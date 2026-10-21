# abc-sim-spell-fish-i00-standard

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `abc-sim-spell-fish-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `spell_fish` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` |

## Task
ABC Sim `spell_fish` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Spell **FISH**: put the blocks F, I, S, H in a row on the table, in this order, reading from left to right as the arms face the table. Success: for every pair of consecutive letters of FISH, the next block's centre is 0.015-0.06 m to the right (-y) of the previous one's and within 0.03 m of it front to back; every block of the word rests on the table (its centre within 0.02 m of the height of a block lying on the table: not stacked, not held up) with a letter face up or down (the axis through its two letter faces within 32 deg of vertical; the letter's rotation within the face is not checked). The other blocks do not matter. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
Twenty-six wooden letter blocks (A to Z, 3 cm cubes; each letter is printed on two opposite faces) lie on the table, letter face up. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. Long-horizon pick and place: 4 blocks found among 26 by their printed letters (the letters are only visible from above and from the side), grasped from a cluttered layout and placed in a tight row, each within a few centimetres, on a table both arms share. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 675 rows, streamed as `joint_position` chunks through the client (`solution/oracle_stream.py`); the service executes exactly those rows and ends at the same state as the privileged replay.

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
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `288971f6896c9bfd`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `spell_fish` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.

### Change Log
- 2026-10-21: first version.
