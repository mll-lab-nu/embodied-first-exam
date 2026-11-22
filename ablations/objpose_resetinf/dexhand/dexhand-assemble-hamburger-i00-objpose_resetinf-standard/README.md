# dexhand-assemble-hamburger-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-assemble-hamburger-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `assemble_hamburger` / seed 0 |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory (privileged: 6,090 controls, success after 5,794; standard: the recorded 5,793-control public-client episode). Both pass two fresh-process replays with identical state hashes. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (5,847 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
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
client, submitted through `rcb_client` in 250-row chunks. The authoring controller that produced it computes robot kinematics and motor targets only; it never
drives an object pose or applies an object force, and it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (5,847 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent: an ingredient touching the table or floor, falling below the table top or
leaving the workspace box, a cheese/lettuce bend above 0.65 rad, unstable physics, or the 7,500-control budget.
The frozen recipe and thresholds come from the task, never from an agent archive. A no-op fails. Human review and
full agent-trial calibration remain pending; report this task as provisional.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task.
The Sharpa Wave assets are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0),
derived from Sharpa Robotics commit `6eea427eb24189519f32b9f21674cd534d3f973c`; finger inertias, geometry, limits
and effort bounds are retained. The Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to wuji-technology/wuji-description
commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist stage with its vendor joints,
actuators and contact geometry unchanged. Ingredient visuals are original procedural geometry. Bun halves, patty and
tomato have rigid cylinder contacts; cheese and lettuce have three passive elastic strips. This is an articulated
approximation of thin-sheet bending, not continuum soft-food, crushing or tearing simulation. The bottom bun starts on
the plate; preparation supports give access to the other ingredients. This is assembly feasibility on a floating wrist
stage, not a gripper-superiority, full-arm or zero-shot claim.
