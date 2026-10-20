# dexhand-assemble-hamburger-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-assemble-hamburger-i00-standard` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `assemble_hamburger` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory (privileged: 6,090 controls, success after 5,794; standard: the recorded 5,793-control public-client episode). Both pass two fresh-process replays with identical state hashes. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (5,847 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Assemble a neat hamburger on the serving plate. The bottom bun already rests on the plate; the beef patty, cheese slice, tomato slice, lettuce leaf and top bun start separately on preparation supports. Stack them from bottom to top in exactly this order: bottom bun, patty, cheese, tomato, lettuce, top bun. Success requires all six layers at the same time: every ingredient center within 12 mm horizontally of the plate center, every layer upright within 0.22 radians, heights strictly increasing in recipe order, all five consecutive pairs in physical contact and the bottom bun touching the plate. Then release the hamburger: with no hand contact on any ingredient, every ingredient linear speed at most 0.025 m/s and angular speed at most 0.25 rad/s, the complete condition must hold for 100 consecutive controls (2 s). The episode ends with success at that moment; a partial stack never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when any ingredient touches the table top or the floor (dropped, or knocked off its support, the plate or the stack), when any ingredient body falls below the table top (z < 0.30 m) or leaves the workspace box x in [-0.64, 0.64] m, y in [-0.52, 0.52] m, z in [0.30, 0.80] m, when a passive cheese or lettuce bending angle exceeds 0.65 radians, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct ingredient forces. Lettuce and cheese use three passive elastic strips; other ingredients are rigid contact proxies. This task evaluates assembly under that approximation, not continuum food deformation or ingredient damage. The episode allows at most 7500 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
Thin layers need controlled contact pickup, transport and release, and every later placement must preserve the
earlier layers. The predicate checks all six centers, the complete recipe order, five neighboring contacts, the bun on
the plate and a released stable hold. Any dropped, fallen or escaped ingredient ends the episode as a failure at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory: in privileged mode the 6,090-control witness
(the replay ends at success after 5,794 controls), in standard mode the recorded 5,793-control episode of the public
client, submitted through `rcb_client` in 250-row chunks. The authoring controller that produced it
(`scripts/dexhand/families/assemble_hamburger/demo.py`) computes robot kinematics and motor targets only; it never
drives an object pose or applies an object force, and it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (5,847 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: an ingredient touching the table or floor, falling below the table top or
leaving the workspace box, a cheese/lettuce bend above 0.65 rad, unstable physics, or the 7,500-control budget.
The frozen recipe and thresholds come from the task, never from an agent archive. A no-op fails. Human review and
full agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: 30 Harbor 0.23 trials of the six essential families (12 oracle, 12 nop, 6 Wuji smoke; rcb_monitor samples every 5 s, efe:dexhand-0.2.0, CPU-only, 2026-10-14) plus the hamburger and paper oracle/nop trials: agent container peak <= 0.03 GiB; one fresh replay process 0.25-0.32 GiB max RSS (os.wait4; paper 0.31 GiB, hamburger 0.28 GiB), the privileged verifier runs two at once (<= 0.65 GiB); standard sim service peak 0.65 GiB (VmHWM, held_joystick oracle episode), paper 0.51 GiB; one core per replay process; x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run about twenty 0.3 GiB simulator sessions (pot/sweep: three or four 2 GiB sessions) next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/assemble_hamburger/`, generated by `scripts/dexhand/generate.py`.
The Sharpa Wave assets are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0),
derived from Sharpa Robotics commit `6eea427eb24189519f32b9f21674cd534d3f973c`; finger inertias, geometry, limits
and effort bounds are retained. The Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to wuji-technology/wuji-description
commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist stage with its vendor joints,
actuators and contact geometry unchanged. Ingredient visuals are original procedural geometry. Bun halves, patty and
tomato have rigid cylinder contacts; cheese and lettuce have three passive elastic strips. This is an articulated
approximation of thin-sheet bending, not continuum soft-food, crushing or tearing simulation. The bottom bun starts on
the plate; preparation supports give access to the other ingredients. This is assembly feasibility on a floating wrist
stage, not a gripper-superiority, full-arm or zero-shot claim.

### Change Log
- 2026-10-16 (video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The verdict, the replays and `reward.json` are unchanged; earlier results stay valid.
