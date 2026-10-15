# dexhand-remote-battery-swap-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-remote-battery-swap-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `remote_battery_swap` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory (2,250 controls; success after 2,100, the last 150 rows are hold slack) in both modes: two fresh-process replays with identical state hashes, also with the rows rounded to float32; standard mode streams the same rows through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Replace the battery of a TV remote that lies on the table. The remote's sliding battery door is closed over a one-cell compartment holding an old gray AA cell; a new green AA cell lies on the table and an empty receiving tray stands beside the remote. In this order: (1) slide the door open until it is at least 0.060 m open (full travel 0.085 m); (2) move the gray cell out of the compartment into the tray, where it must rest on the tray floor: its centre inside the tray's inner box (|x| <= 0.037 m, |y| <= 0.032 m in the tray frame) and at most 0.014 m above the tray origin (the floor top is 0.003 m above the origin; a resting cell's centre is about 0.010 m above it), touching the tray floor, with no hand contact; (3) seat the green cell in the compartment slot with correct polarity: its centre within 5 mm (along the slot), 3 mm (across) and 2 mm (height) of the slot centre, lying on both cradle ribs, and its + end toward the gold contact (cell axis within 10 degrees of the remote's long axis, + end at the gold contact); (4) slide the door shut (at most 0.004 m open). Then release everything: with no hand contact on the remote, door, tray or either cell, the gray cell still in the tray, the green cell still seated, the door still shut and every task object at rest (linear speed of its body origin <= 0.02 m/s, angular speed <= 0.5 rad/s; for the cells and the tray the origin is the centre of mass), the condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; each stage counts only after the previous ones, and partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when any cell, the door, the remote or the tray falls below the table top (z < 0.30 m) or leaves the workspace box x in [-0.37, 0.47] m, y in [-0.34, 0.34] m, z in [0.30, 0.80] m, when any of them touches the floor, when the remote slides more than 0.03 m or tilts more than 15 degrees, when the tray slides more than 0.03 m or tilts more than 15 degrees, when the gray cell touches the table top, when the green cell touches the table top again after it has been lifted (lifted: at a control it is clear of the table and its centre is more than 0.01 m above its start height), when a cell without hand contact moves down faster than 0.886 m/s (the speed of a free drop from 0.04 m), or a cell touching nothing at all (no hand, no surface) moves down faster than 0.5 m/s (there is no grace period; a later catch does not undo it), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
Four ordered contact operations with one hand on a floating wrist stage: sliding a friction-held battery door with a
fingertip, a precision pinch of a 14 mm cell out of a one-cell compartment, placing it in a tray without dropping it,
picking a second cell off the flat table, turning it so its + end faces the gold contact and lowering it onto the
slot's cradle ribs (3 mm end play), then sliding the door shut and letting go of everything for a second. The remote
and the tray are free bodies that must not be shoved or tipped, and a cell that touches the table at the wrong time,
or falls freely (faster than 0.5 m/s with no contact), fails the episode at once. Reversed polarity, a skewed or raised cell, a door left open
or a partial sequence never count.

## Reference solution
`solution/trajectory.npz` replays a validated Sharpa Wave authoring trajectory: 2,250 motor-target rows; the replay
ends with success after 2,100 controls (the last 150 rows are hold slack). In privileged mode the oracle copies the
rows to `/app/output/trajectory.npz`; in standard mode it streams the same rows as float64 through `rcb_client` in
250-row chunks. The authoring controller that produced it (`scripts/dexhand/families/remote_battery_swap/demo.py`)
plans fingertip positions with inverse kinematics from simulator state and emits plain actuator targets only; it
never drives an object pose or applies an object force, and it is never copied into the agent's environment or image.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final state hashes; in standard mode the replay
hash must also equal the live final hash. A replay ends at the first success or the first failure. Failures are
fail-fast and permanent and are checked after every 2 ms physics substep: a cell, the door, the remote or the tray
below the table top or outside the workspace box, any of them touching the floor, the remote or the tray moved more
than 3 cm or tilted more than 15 degrees, the gray cell touching the table, the green cell touching the table again
after it was lifted, a cell without hand contact moving down faster than 0.886 m/s (a drop from more than 4 cm), a
cell touching nothing at all moving down faster than 0.5 m/s (no catch window), unstable physics, or the 6,000-control
budget. The frozen instance and thresholds come from the task, never from an agent archive. A no-op
fails. Human review and full agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 0.96 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/remote_battery_swap/`, generated by `scripts/dexhand/generate.py`, from scene T07
"Remote battery replacement" of the scene expansion (an approved kinematic film with prescribed object motion). The
approved presentation meshes of the remote shell, battery door, thumb pad and OPEN arrow and the two AA wrap textures
are copied with sha256 in `assets/manifest.json`; the cell label mesh is original. Simplifications that keep the
scene's objects, look and goal: the remote shell is widened 1.25 times across (80 mm, cavity 65 mm) so two fingertips
fit beside one cell; the compartment holds one cell; the original door latch tab and the compressible negative spring
are not modelled (the door is a passive slide joint, 0.085 m travel with end stops, held by 0.25 N of friction loss,
with a 3 mm thumb ridge; the terminals are fixed); there is no electrical simulation. The remote (0.35 kg, rubber
feet), the tray (0.12 kg) and the cells (23 g rigid cylinders) are free bodies. The Sharpa Wave assets are pinned to
MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model
(`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702`
(MIT) and mounted on the same wrist stage with its vendor joints, actuators and contact geometry unchanged. This is
manipulation feasibility on a floating wrist stage, not a full-arm or zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
