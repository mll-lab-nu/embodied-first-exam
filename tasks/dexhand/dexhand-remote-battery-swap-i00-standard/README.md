# DexHand · Replace the battery of a TV remote (standard)

| | |
|---|---|
| Task ID | `dexhand-remote-battery-swap-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `remote_battery_swap`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Replace the battery of a TV remote that lies on the table.

## Success criteria
The door's slide is how far the battery door is slid open from its closed position. The robot means any part of the
arms, hands or stand; the remote includes its door. Four stages, in this order, checked at the end of each control
step (50 Hz); each counts once it has been met, and at most one stage is reached per control step:
1. Door open: the door is slid open at least 60 mm.
2. Old cell in the tray: the gray cell's centre, in the tray's frame, is within 37 mm (x) and 32 mm (y) of the tray
   centre and at most 14 mm above it; the cell touches the tray floor; and the robot does not touch it.
3. New cell seated: the green cell's centre, in the remote's frame, is within 5 mm (x), 3 mm (y) and 2 mm (z) of the
   slot centre; its + end points toward the gold contact, its axis within 10° of the slot axis; it touches both
   cradle ribs; and the robot does not touch it.
4. Door closed: the door's slide is at most 2 mm and the latch tab is back up, pressed in at most 1.5 mm.

Then, held for 50 consecutive control steps (1 s): stages 2, 3 and 4 are all met again (the door may not reopen); the
robot touches neither the remote, the tray nor a cell; and the remote, the tray and both cells each move at most
0.02 m/s and turn at most 0.5 rad/s.

The new cell counts as lifted once, at the end of a control step, its centre is more than 10 mm above its start height
and it does not touch the table. The episode fails at once, checked after every 2 ms physics substep, when: a cell,
the door, the remote or the tray has its origin below the table top (z = 0.3 m) or outside the work box x -0.37 to
0.47 m, y -0.34 to 0.34 m, z 0.3 to 0.8 m, or touches the floor; the remote or the tray moves more than 30 mm sideways
or tilts more than 15° from its start; the parked left arm or the left hand touches the remote, the tray or a cell;
the gray cell touches the table top; the green cell touches the table top after it has been lifted; a cell falls
faster than 0.886 m/s (a drop from 40 mm) while the robot does not touch it, or faster than 0.5 m/s while it touches
nothing; or the physics becomes unstable. The step budget is 6,000 control steps (120 s).

Graded is the live episode on the simulator service; nothing is replayed. The service runs the hand the runner
selects (Sharpa Wave unless the Wuji Hand 2.2 is selected; `spec()["hand"]` names it). The agent may reset up to
20 times, each reset starting a new episode from the same frozen start; only the last episode is graded. An
episode ends at the agent's `POST /finish`, when the agent's session ends (at the latest after 1 h), at the first
failure above (a score of 0), at the step budget where the task has one, or on a simulator error (a score of 0). A
success neither ends the episode nor is shown to the agent.

Each stage before the last counts at the moment it is completed. The last stage, with its full hold, must be met on
the state the episode ends in: every check goes on after it is first met, and a failure after it still scores 0. If
it is not met at `/finish` or at the session's end, the robot holds its current targets for up to 3 s of simulated
time, and the episode passes if the last stage completes within that time without a failure. At the step budget it
must be met at that step. Targets outside an actuator's range are clipped. Each episode's start is checked against
the frozen instance; a mismatch is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 7 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## License
DexHand's scenes, checkers and graders are original to this repository (MIT License). Robot models: the Sharpa Wave
hand from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/0059d4335f8156206f63a35662313385f7ad6d74/sharpa_wave)
@ `0059d43` (Apache License 2.0); the Wuji Hand 2.2 from
[wuji-technology/wuji-description](https://github.com/wuji-technology/wuji-description/tree/829c9aa27cb12c3a49d5b8d63c9869dd8f656702)
@ `829c9aa` (MIT License); the Tianji Marvin arm meshes from DexForce `embodichain_data` (Apache License 2.0) with
inertias from Genesis' `dual_arms_primitives.urdf` (MIT License), see `images/dexhand/tianji/NOTICE.md`. Object
assets are original geometry of this repository, CC0 (the Poly Haven rubber boot, the Innerscene stockpot, Monet's
public-domain Water Lilies, original page and letter artwork) or CC BY 4.0 (the Joy-Con, pen, rotary-knob and walnut
meshes; credits in each task's `object_assets/*/CREDITS.txt`); printed text uses the DejaVu fonts (Bitstream Vera
license). No non-commercial terms apply.
