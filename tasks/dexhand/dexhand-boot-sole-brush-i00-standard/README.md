# DexHand · Brush the debris off a boot sole (standard)

| | |
|---|---|
| Task ID | `dexhand-boot-sole-brush-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `boot_sole_brush`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Brush all six soil clods off the upward-facing sole of the boot into the collection tray.

## Success criteria
Three stages, in this order, checked at the end of each control step (50 Hz). A clod is in the tray when its origin
lies inside the tray's walls (x 0.366 to 0.694 m, y -0.184 to 0.384 m) and between the counter top (z = 0.886 m) and
the top of the walls (z = 0.931 m).
1. Brushed: for at least 10 control steps in all (not necessarily in a row), the brush's bristle pad touches the
   boot while the hand touches the brush and the brush does not touch the counter.
2. Clean: all six clods are in the tray, however they got there.
3. Withdrawn, for 50 consecutive control steps (1 s): all six clods are in the tray and each moves at most 0.05 m/s;
   the brush touches neither the boot nor a clod, and its bristle pad's centre is at least 0.04 m above the boot's
   origin (the sole plane) or at least 0.18 m from it horizontally.

The episode fails at once, checked after every 2 ms physics substep, when: any part of the robot other than its right
hand (the stand, the torso, an arm link or flange, the parked left hand) touches anything, the robot itself included;
the boot's origin moves more than 30 mm from its start or its axis tilts more than 0.35 rad; a clod's or the brush's
origin goes below the counter top or leaves the box x 0.25 to 1.20 m, y -0.45 to 0.45 m, z 0.886 to 1.80 m; a clod
touches the counter or the floor; any part of the right hand touches a clod; the brush touches the floor, the tray or
the rack; the brush touches nothing but clods while its centre of mass falls faster than 0.2 m/s; or the physics
becomes unstable. The step budget is 3,000 control steps (60 s).

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
