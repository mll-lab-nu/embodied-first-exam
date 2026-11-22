# dexhand-remote-battery-swap-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-remote-battery-swap-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `remote_battery_swap` / seed 0 |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory on the Marvin right arm (2,416 controls; success after 2,266, the last 150 rows are hold slack) in both modes: two fresh-process replays with identical state hashes, also with the rows rounded to float32; standard mode streams the same rows through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Replace the battery of a TV remote that lies on the table. The remote's sliding battery door is shut and latched over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on the table and an empty receiving tray stands beside the remote. In this order: (1) release the door latch by pressing the door's spring-loaded thumb tab down and slide the door open until it is at least 0.060 m open (full travel 0.085 m); (2) move the gray cell out of the compartment into the tray, where it must rest on the tray floor: its centre inside the tray's inner box (|x| <= 0.037 m, |y| <= 0.032 m in the tray frame) and at most 0.014 m above the tray origin (the floor top is 0.003 m above the origin; a resting cell's centre is about 0.010 m above it), touching the tray floor, with no hand contact; (3) seat the green cell in the compartment slot with correct polarity: its centre within 5 mm (along the slot), 3 mm (across) and 2 mm (height) of the slot centre, lying on both cradle ribs, and its + end toward the gold contact (cell axis within 10 degrees of the remote's long axis, + end at the gold contact); (4) slide the door shut and let the latch engage: at most 0.002 m open with the thumb tab released (pressed at most 0.0015 m), so its hook sits in front of the latch stop. Then release everything: with no hand contact on the remote, door, tray or either cell, the gray cell still in the tray, the green cell still seated, the door still shut and latched and every task object at rest (linear speed of its body origin <= 0.02 m/s, angular speed <= 0.5 rad/s; for the cells and the tray the origin is the centre of mass), the condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; each stage counts only after the previous ones, and partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when any cell, the door, the remote or the tray falls below the table top (z < 0.30 m) or leaves the workspace box x in [-0.37, 0.47] m, y in [-0.34, 0.34] m, z in [0.30, 0.80] m, when any of them touches the floor, when the remote slides more than 0.03 m or tilts more than 15 degrees, when the tray slides more than 0.03 m or tilts more than 15 degrees, when the gray cell touches the table top, when the green cell touches the table top again after it has been lifted (lifted: at a control it is clear of the table and its centre is more than 0.01 m above its start height), when a cell without hand contact moves down faster than 0.886 m/s (the speed of a free drop from 0.04 m), or a cell touching nothing at all (no hand, no surface) moves down faster than 0.5 m/s (there is no grace period; a later catch does not undo it), when the parked left arm or the left hand touches the remote, its door, the tray or a cell (left_arm_contact; moving the left arm is not blocked, but the task is done by the right arm and hand), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets (arm joints and fingers) are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
Four ordered contact operations with one hand on a 7-joint arm (Tianji Marvin, no gravity compensation): pressing
the door's spring-loaded latch tab 3-4.5 mm deep while sliding the battery door open (and again to slide it shut and
let it latch), a precision pinch of a 14 mm cell out of a one-cell compartment, placing it in a tray without dropping it,
picking a second cell off the flat table, turning it so its + end faces the gold contact and lowering it onto the
slot's cradle ribs (3 mm end play), then sliding the door shut and letting go of everything for a second. The remote
and the tray are free bodies that must not be shoved or tipped, and a cell that touches the table at the wrong time,
or falls freely (faster than 0.5 m/s with no contact), fails the episode at once. Reversed polarity, a skewed or raised cell, a door left open
or a partial sequence never count.

## Reference solution
`solution/trajectory.npz` replays a validated Sharpa Wave authoring trajectory on the Marvin right arm: 2,416
motor-target rows; the replay ends with success after 2,266 controls (the last 150 rows are hold slack). In privileged mode the oracle copies the
rows to `/app/output/trajectory.npz`; in standard mode it streams the same rows as float64 through `rcb_client` in
250-row chunks. The authoring controller that produced it
plans fingertip positions with inverse kinematics over the arm and finger joints from simulator state and emits plain
actuator targets only; it
never drives an object pose or applies an object force, and it is never copied into the agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure. Failures are
fail-fast and permanent and are checked after every 2 ms physics substep: a cell, the door, the remote or the tray
below the table top or outside the workspace box, any of them touching the floor, the remote or the tray moved more
than 3 cm or tilted more than 15 degrees, the gray cell touching the table, the green cell touching the table again
after it was lifted, a cell without hand contact moving down faster than 0.886 m/s (a drop from more than 4 cm), a
cell touching nothing at all moving down faster than 0.5 m/s (no catch window), the parked left arm or left hand touching a task object, unstable physics, or the 6,000-control
budget. The frozen instance and thresholds come from the task, never from an agent archive. A no-op
fails. Human review and full agent-trial calibration remain pending; report this task as provisional.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 7 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task, from scene T07
"Remote battery replacement" of the scene expansion (an approved kinematic film with prescribed object motion). The
approved presentation meshes of the remote shell, battery door, thumb pad and OPEN arrow and the two AA wrap textures
are copied with sha256 in `assets/manifest.json`; the cell label mesh is original. The source geometry is kept: the
remote at its source size (shell 160 x 64 mm, cavity 94 x 52 mm), the door's source latch (spring-loaded thumb tab,
5 mm travel, 120 N/m, with a hook in front of a fixed latch stop; source door damping 0.1 and friction 0.08 N), the
source's one-cell compartment with one gray cell, one green cell on the table and the tray. Documented modelling
choices: two 1.5 mm cradle ribs and fixed end terminals (3 mm play) instead of the source's compressible negative
spring; rigid cells; no electrical simulation. The remote (0.35 kg, rubber feet), the tray (0.12 kg) and the cells
(23 g rigid cylinders) are free bodies. The robot is the Tianji Marvin stand of `pot_shelf_transfer` (two 7-DoF arms,
position servos kp 700 / kv 48, pinned Tianji meshes) with a hand on each flange, placed at the table like the source
scene's robot; the left arm is parked. The Sharpa Wave assets are pinned to
MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model
(`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702`
(MIT) and mounted on the same arm flanges with its vendor joints, actuators and contact geometry unchanged. This is
manipulation feasibility with an arm-mounted hand in simulation, not a zero-shot or real-robot claim.
