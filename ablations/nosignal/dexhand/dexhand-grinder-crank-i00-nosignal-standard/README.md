# dexhand-grinder-crank-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-grinder-crank-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `grinder_crank` / seed 0 |
| Oracle | `full` — solution/trajectory.npz: 1,096 Sharpa Wave rows on the Marvin dual-arm robot (success after 996 controls, 100 rows of slack), recorded from the authoring controller through its arm layer (IK to arm joint targets; motor targets only). Two fresh-process replays end with identical state hashes; float32-rounded rows also succeed. Wave-3 port of the 2026-10-14 floating-stage oracle. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Operate the manual coffee grinder on the counter with the two hands of the dual-arm robot standing at the counter. The HARIO-style hand mill (0.40 kg, 174 mm body, 26 mm base radius) stands free on the counter top (z = 0.70 m) with its base centre at (0.45, 0, 0.70) m. Its crank turns on a passive hinge about the grinder axis with grinding resistance (0.08 N m dry friction and 0.012 N m s/rad damping); the knob sits on a free spin bearing at 80 mm crank radius. The grinder is light and narrow: it tips over if the crank is driven without holding the body. Hold the grinder body with one hand and turn the crank by its knob with the other until the crank has turned at least two full turns (720 degrees) net clockwise as seen from above, measured as the unwrapped crank hinge angle relative to the grinder body. Then let go of the grinder. Success requires, at the same time: the crank still at least 720 degrees net clockwise, no contact between any part of either hand and any part of the grinder (body, crank or knob), the grinder base resting on the counter, the grinder axis within 10 degrees of vertical, grinder centre-of-mass linear speed at most 0.02 m/s, grinder angular speed at most 0.2 rad/s and crank speed at most 0.5 rad/s; this complete condition must hold for 50 consecutive controls (1 s). The episode ends with success at that moment; turning the crank without the released hold never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the grinder axis tilts more than 10 degrees from vertical, the grinder base moves more than 2 cm horizontally from its start or rises more than 2 cm, the base falls below the counter top (z < 0.695 m), the grinder body turns more than 45 degrees about its own axis, the crank has turned more than 90 degrees net counter-clockwise, an arm, torso or stand link of the robot touches anything (only the hands may make contact), or the physics becomes unstable; later actions cannot undo a failure. Only the robot's actuator targets (14 arm joints and the fingers of both hands) are allowed: no object teleports, grasp welds, scripted object motion or direct forces on the grinder. Grinding itself is summarised by the crank angle; no beans or grounds are simulated. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The grinder is a light, narrow, free-standing body: driving the friction-loaded crank without a counterhold tips it
over or spins it, so the robot's two hands must cooperate (no arm link may touch anything). One hand has to hold the body without pushing it over or off its
spot; the other has to keep a pinch on a small knob that orbits at 80 mm radius and on a free spin bearing, through
two full turns in the right direction. Both hands must then let go without dragging the grinder, which must stand at
rest by itself for a full second. Any tip, slide, lift, body spin or crank reversal ends the episode at once.

## Reference solution
`solution/trajectory.npz` replays the validated two-hand Sharpa Wave trajectory on the dual-arm robot: 1,096 controls,
the episode ends at success after 996 (100 hold rows of slack). In privileged mode the oracle hands these rows in; in
standard mode it submits the same rows as float64 through `rcb_client`. The left hand wraps the grinder's receptacle
from the robot's left side, the right hand pinches the knob from above and its wrist follows the knob circle clockwise
for 2.06 turns, then both hands let go and withdraw. The rows come from a closed-loop scripted authoring controller
that reads simulator state only to choose hand poses and finger targets, converted into the 14 arm joint targets by
inverse kinematics; it never drives an object pose or applies an object force, and it is never copied into the
agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure. Failures are fail-fast and permanent: grinder tilt above 10 degrees, base slide above 2 cm, lift above 2 cm,
base below the counter top, body rotation above 45 degrees about its axis, crank more than 90 degrees net
counter-clockwise, any arm/torso/stand link contact, unstable physics, or the 3,000-control budget. The frozen thresholds come from the task, never from
an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

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
Source: the DexHand family of this task. The grinder geometry,
materials, masses, inertias and passive crank/knob joints are the unchanged T15 scene source (`assets/source/
hario_mechanism.py`, HARIO MSS-1DTB-style, author-estimated dimensions, no manufacturer CAD); task overrides are the
crank/knob armature, a rubber-like knob friction of 1.0, internal shaft/burr excluded from contact and multi-point
convex contacts. Grinding is a reduced passive hinge load (0.08 N m dry friction, 0.012 N m s/rad damping); no beans,
fracture or grounds are simulated and progress is the crank angle. The Sharpa Wave assets are pinned to MuJoCo
Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the left Sharpa Wave is the declared
reflection of the right model in y (as in the accepted bimanual families). The Wuji Hand 2.2 models (`hand2/hand2_2`,
left and right) are pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT)
and mounted on the same flanges with their vendor joints, actuators and contact geometry unchanged. The robot is the
Tianji Marvin dual-arm stand of the accepted pot_shelf_transfer family (two 7-joint arms, position servos kp 700 N m/rad,
kv 48, force limits 108/108/66/66/18/18/18 N m, Tianji meshes pinned in the image) behind the counter; each hand sits
rigidly on its arm's flange. This is a simulated two-hand operation, not a zero-shot hardware claim.
