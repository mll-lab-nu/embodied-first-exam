# dexhand-pancake-serve-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-pancake-serve-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `pancake_serve` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory on the Marvin arm rig (1,167 controls; the turner is picked up from the counter, the replay ends at success after 1,017 controls) in both modes; it succeeds in two fresh processes with identical state hashes, also with float32-rounded rows. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Serve the pancake from the frying pan onto the plate using the kitchen turner (spatula). The turner starts resting on the counter in front of the plate, as in the source scene; pick it up with a hand of the two-arm robot first (both hands start open). The pancake lies in the frying pan, the empty ceramic plate stands beside it on the counter. Only the turner may move the pancake: slide its blade under the pancake, lift it out of the pan on the blade, carry it to the plate, set it down in the plate and withdraw the turner. Success requires three stages in this order. (1) On the blade: the pancake touches the turner blade and no other object (no pan, plate, hand, counter or floor contact), its origin is at least 0.015 m above its starting height and it is tilted at most 30 degrees, for 10 consecutive controls. (2) Over the plate: later, while still touching only the turner, the pancake centre is within 0.058 m (horizontally) of the plate centre and above the plate floor. (3) Served: later, the pancake touches only the plate, its centre is within 0.058 m of the plate centre horizontally (the whole pancake inside the plate's 0.128 m rim radius), it is tilted at most 20 degrees from flat, its linear speed is at most 0.02 m/s and angular speed at most 0.3 rad/s, the turner does not touch it and every point of the blade outline is at least 0.08 m from the pancake centre horizontally (withdrawn); this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; skipping or reordering a stage never counts. The episode ends immediately with failure, checked after every 1 ms physics substep with no grace period, when the pancake touches the counter top or the floor, falls freely (touching nothing while its centre of mass moves down faster than 0.35 m/s, i.e. after about 6 mm of free fall) or its origin falls below the counter top (z < 0.85 m), when any part of the robot (hands, arm links, stand) touches the pancake, when the turner touches the floor, falls out of the hand (no hand contact while its centre of mass moves down faster than 0.35 m/s) or its origin falls below the counter top, when the pan or the plate moves more than 0.03 m from its starting position or tilts more than 15 degrees, when the pancake, pan, plate or turner leaves the workspace box x in [0.23, 1.13] m, y in [-0.65, 0.45] m, z in [0.80, 1.50] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The pancake is a rigid coherent disk and the turner blade bends through three passive spring hinges. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The turner is a tool held only by contact: its flexible blade has to be landed steeply over the pan wall, pressed so
its passive strips flatten on the pan floor, and slid under a rigid pancake without pushing it up the far wall. The
pancake then rides on a low-friction blade that is narrower than the pancake, so lifting, carrying and setting it
down need controlled blade pitch and gentle accelerations, and the turner must be withdrawn without dragging the
pancake off the plate. Any drop onto the counter, direct hand contact with the food, or a knocked pan or plate ends
the episode as a failure at once.

## Reference solution
`solution/trajectory.npz` replays a physical serving trajectory of the Sharpa Wave on the right Marvin arm (1,167 rows;
the replay ends at success after 1,017 controls, the remaining rows hold the robot still). It was recorded from an
authoring controller (`scripts/dexhand/families/pancake_serve/tools/pickup_arm.py` with `tools/demo_arm.py`): the open
right hand comes down palm-first over the resting turner's handle near its neck, closes a power grasp and lifts the
turner, then the hand pose is computed every control from the measured turner pose so that the blade follows scripted
waypoints (nudge the pancake off the near wall, slide under it, scoop, lift, carry, lower into the plate, tilt and
withdraw), converted to arm joint targets by damped least-squares IK with a joint integral; it records plain actuator
targets, never sets an object pose or applies an object force, and is never copied into the agent's environment or
image.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent, checked after every 1 ms substep with no grace window: the pancake touching
the counter or floor, falling freely (touching nothing while moving down faster than 0.35 m/s) or falling below the
counter top, any hand contact with the pancake, the turner on the floor, falling out of the hand or below the counter
top, the pan or plate moved more than 3 cm or tilted more than 15 degrees, a task body leaving the workspace box,
unstable physics, or the 3,000-control budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails. Human review and full
agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 5 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/pancake_serve/`, generated by `scripts/dexhand/generate.py`. The scene is the T16
"Serve food from a frying pan with a spatula" scene: Fiskars Hard Face 22 cm pan, OXO Good Grips large flexible
turner (SKU 1071534), ceramic plate and a coherent cooked pancake; their meshes and texture are copied unchanged
(sha256 manifest in `assets/manifest.json`). Masses, inertias and the turner's three passive bending strips follow
the source; pan and plate interiors use convex sector contacts. Pair frictions are declared estimates (pancake-pan
0.45, pancake-blade 0.20, blade-pan 0.20, pancake-plate 0.60, grip 1.2). The pancake is rigid: no deformation,
tearing, heat or fluid model. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same
flanges. The robot is the Tianji Marvin stand of `pot_shelf_transfer` (two 7-DoF position-servo arms, no gravity
compensation) at the world origin facing +x; the right arm serves, the left arm is parked (`arm_rig.py`). The turner
starts at rest on the counter at the source's pose (settled under physics) and must be picked up; there is no weld.
Not reproduced from the source: the other hand supporting and tilting the pan (about 8 degrees and 4 cm in the source
film); here the pan stands free and the left arm stays parked. This is a physical tool-use task for an arm-mounted
dexterous hand, not a zero-shot claim.

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
