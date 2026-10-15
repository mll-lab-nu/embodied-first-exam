# dexhand-grinder-crank-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-grinder-crank-i00-standard` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating-bimanual` |
| Family / instance | `grinder_crank` |
| Oracle | `full` — solution/trajectory.npz replays the validated two-hand Sharpa Wave authoring trajectory (854 controls, success after 754, 100 hold rows of slack) produced by a closed-loop scripted controller that only chooses motor targets; it passes two fresh-process replays with identical state hashes and also succeeds with float32-rounded rows. The standard oracle submits the same rows as float64 through the public client. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (1,005 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Operate the manual coffee grinder on the counter with your two hands. The HARIO-style hand mill (0.40 kg, 174 mm body, 26 mm base radius) stands free on the counter top (z = 0.70 m) with its base centre at (0.45, 0, 0.70) m. Its crank turns on a passive hinge about the grinder axis with grinding resistance (0.08 N m dry friction and 0.012 N m s/rad damping); the knob sits on a free spin bearing at 80 mm crank radius. The grinder is light and narrow: it tips over if the crank is driven without holding the body. Hold the grinder body with one hand and turn the crank by its knob with the other until the crank has turned at least two full turns (720 degrees) net clockwise as seen from above, measured as the unwrapped crank hinge angle relative to the grinder body. Then let go of the grinder. Success requires, at the same time: the crank still at least 720 degrees net clockwise, no contact between any part of either hand and any part of the grinder (body, crank or knob), the grinder base resting on the counter, the grinder axis within 10 degrees of vertical, grinder centre-of-mass linear speed at most 0.02 m/s, grinder angular speed at most 0.2 rad/s and crank speed at most 0.5 rad/s; this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; turning the crank without the released hold never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the grinder axis tilts more than 10 degrees from vertical, the grinder base moves more than 2 cm horizontally from its start or rises more than 2 cm, the base falls below the counter top (z < 0.695 m), the grinder body turns more than 45 degrees about its own axis, the crank has turned more than 90 degrees net counter-clockwise, or the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed: no object teleports, grasp welds, scripted object motion or direct forces on the grinder. Grinding itself is summarised by the crank angle; no beans or grounds are simulated. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The grinder is a light, narrow, free-standing body: driving the friction-loaded crank without a counterhold tips it
over or spins it, so the two hands must cooperate. One hand has to hold the body without pushing it over or off its
spot; the other has to keep a pinch on a small knob that orbits at 80 mm radius and on a free spin bearing, through
two full turns in the right direction. Both hands must then let go without dragging the grinder, which must stand at
rest by itself for a full second. Any tip, slide, lift, body spin or crank reversal ends the episode at once.

## Reference solution
`solution/trajectory.npz` replays the validated two-hand Sharpa Wave authoring trajectory: 854 controls, the episode
ends at success after 754 (100 hold rows of slack). In privileged mode the oracle hands these rows in; in standard mode
it submits the same rows as float64 through `rcb_client`. The left hand wraps the grinder's receptacle (thumb in
front, fingers around the back), the right hand pinches the knob from above and its wrist follows the knob circle
clockwise for 2.07 turns, then both hands let go and withdraw. The rows come from a closed-loop scripted authoring
controller that reads simulator state only to choose motor targets; it never drives an object pose or applies an
object force, and it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (1,005 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand model (`hand` member of the trajectory
archive in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor
targets twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in
standard mode the replay hash must also equal the live final hash. A replay ends at the first success or the first
failure. Failures are fail-fast and permanent: grinder tilt above 10 degrees, base slide above 2 cm, lift above 2 cm,
base below the counter top, body rotation above 45 degrees about its axis, crank more than 90 degrees net
counter-clockwise, unstable physics, or the 3,000-control budget. The frozen thresholds come from the task, never from
an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/grinder_crank/`, generated by `scripts/dexhand/generate.py`. The grinder geometry,
materials, masses, inertias and passive crank/knob joints are the unchanged T15 scene source (`assets/source/
hario_mechanism.py`, HARIO MSS-1DTB-style, author-estimated dimensions, no manufacturer CAD); task overrides are the
crank/knob armature, a rubber-like knob friction of 1.0, internal shaft/burr excluded from contact and multi-point
convex contacts. Grinding is a reduced passive hinge load (0.08 N m dry friction, 0.012 N m s/rad damping); no beans,
fracture or grounds are simulated and progress is the crank angle. The Sharpa Wave assets are pinned to MuJoCo
Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the left Sharpa Wave is the declared
reflection of the right model in y (as in the accepted bimanual families). The Wuji Hand 2.2 models (`hand2/hand2_2`,
left and right) are pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT)
and mounted on the same wrist stages with their vendor joints, actuators and contact geometry unchanged. This is a
two-hand operation on floating wrist stages, not a full-arm or zero-shot claim.
