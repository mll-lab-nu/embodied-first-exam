# DexHand · Plug a USB cable into a hub port (standard)

| | |
|---|---|
| Task ID | `dexhand-usb-plug-insert-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `usb_plug_insert`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the cable's plug and lift it a few centimetres off the desk, then plug it into the hub's rightmost port (seen
from the front) with its top face up, and let go.

## Success criteria
Three stages, in this order, checked at the end of each control step (50 Hz). The plug's position is its origin,
measured in the hub's frame from the mouth of a port.
1. Lifted: the thumb and at least one other finger touch the plug, the plug touches nothing but the hand, and its
   origin is at least 30 mm above the desk top (z = 0.73 m or higher).
2. Seated in port 4 (the rightmost port seen from the front): the plug is at least 10.8 mm deep in the port (90 % of
   its 12 mm depth), within 0.6 mm of the port's centre sideways and 0.5 mm in height; its axis is within 5° of the
   port's axis; and its top face is within 20° of the hub's up direction (correct polarity).
3. Released, for 50 consecutive control steps (1 s): the plug is seated in port 4 as in stage 2; the hand touches
   neither the plug, its cable nor the hub; the plug moves at most 0.01 m/s.

The episode fails at once, checked after every 2 ms physics substep, when: an arm link, the stand, the torso or the
parked left hand touches anything; the plug's origin is more than 15 mm below the desk top (z = 0.70 m), or the hub's
below it; the plug's or the hub's origin leaves the box x 0.25 to 1.15 m, y -0.40 to 0.95 m, z 0.685 to 1.10 m; the
hub moves more than 20 mm from its start or tilts more than 20°; the cable's far end is more than 50 mm below the desk
top; or the physics becomes unstable. It also fails, checked at the end of each control step after stage 1, when the
plug is not engaged in any port (at least 3 mm deep and within 4 mm of its centre) and the hand touches neither the
plug nor its cable, while the plug falls faster than 0.2 m/s or touches the desk or the floor. The step budget is
3,000 control steps (60 s).

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
