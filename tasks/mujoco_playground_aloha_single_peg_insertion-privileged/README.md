# mujoco_playground_aloha_single_peg_insertion-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_aloha_single_peg_insertion-standard` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `mujoco_playground/AlohaSinglePegInsertion` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-mujoco:0.1.2` |

## Task
MuJoCo Playground's `AlohaSinglePegInsertion` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (peg tip ≤ 5 mm from the socket axis and inside the cavity at least 12 mm from its open end (axial −0.875 ≤ t ≤ 0.75; t = 0 at the tube's centre, 1 at the entrance, −0.833 at the rear wall) at the end), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: top-down grasps with DLS IK + gravity feedforward, lift, rate-limited visual servo of the peg tip onto the socket axis, push in (tip 1.8 mm from the axis, t = 0.44, 470 control steps)

## Verification
Playground has only a shaped RL reward; defined here from its insertion geometry: peg tip ≤ 5 mm from the socket axis and inside the cavity at least 12 mm from its open end (axial −0.875 ≤ t ≤ 0.75; t = 0 at the tube's centre, 1 at the entrance, −0.833 at the rear wall) at the end

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.0-1.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.6 GB, sim 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU p90 1.9 cores, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + ws-1, 10-10)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 6 GiB GPU memory, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 8 GiB memory. Limits measured: GPU: 1.3 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 8 GiB, which every past trial ran under (docker peak 4.8 GiB over 9 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/aloha/xmls/mjx_single_peg_insertion.xml`; ALOHA 2 from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 400 Hz (Playground's sim_dt), implicitfast; control 50 Hz (8 substeps) |
| instance | Playground's reset randomization (peg, socket xy ± 0.1 m) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward; defined here from its insertion geometry: peg tip ≤ 5 mm from the socket axis and inside the cavity at least 12 mm from its open end (axial −0.875 ≤ t ≤ 0.75; t = 0 at the tube's centre, 1 at the entrance, −0.833 at the rear wall) at the end |
| deliverable | `(T, 14)` actuator targets per control step, T ≤ 3000; bit-exact replay |

### Change Log
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
- 2026-10-13 (board 0086): the success rule's rear bound, and the text. The judge (`environment/rcb_aloha.py`, `tests/rcb_aloha.py`: `Session.check`) required `0 <= t <= 0.75`, while the instruction said only `t ≤ 0.75` and placed t = 0 "at the rear wall". Site `socket_rear` is at the tube's centre; the rear wall's inner face is at t = −0.833. So a peg inserted past the middle of the tube, the fully inserted one included, was graded a failure. The rule is now `−0.875 <= t <= 0.75` (the tip anywhere in the 88 mm cavity up to 12 mm inside its open end; the rear bound is read from the model, with 2 mm for the contact's give), and the instruction and this README state it ("25 % of the depth" was wrong too: 12 mm of 88 mm). The scene, the instance and the 5 mm axis tolerance are unchanged, so the task keeps its name. Every trajectory that passed still passes (the oracle: t = 0.44); a trajectory graded 0 before this date with `tip_to_axis_m` < 0.005 and `axial_t` in [−0.875, 0) is a pass now.
