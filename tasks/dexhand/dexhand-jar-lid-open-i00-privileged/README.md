# DexHand · Open a jam jar and set the lid aside (privileged)

| | |
|---|---|
| Task ID | `dexhand-jar-lid-open-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `jar_lid_open`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Open the jam jar with the robot's right hand, then set the lid upright on the worktop, clear of the jar, and let go.

## Success criteria
Three stages, in this order:
1. Unscrewed: while the lid still sits on the thread (its origin less than 6 mm above its closed height and less than
   4 mm from the jar axis), it has turned counter-clockwise relative to the jar (seen from above) by at least
   1.049 rad, the angle at which every lug has passed its ramp end. The turn is tracked after every 2 ms physics
   substep.
2. Lifted clear: the lowest point of the lid's skirt is more than 30 mm above the jar rim.
3. Set aside, for 50 consecutive control steps (1 s), checked at the end of each control step: the lid touches the
   worktop and touches neither the robot nor the jar; the jar touches the worktop and not the robot; the lid's tilt is
   at most 0.15 rad and the jar's at most 0.10 rad; the lid's centre is at least 90 mm from the jar's centre
   horizontally; the lid moves at most 0.02 m/s and turns at most 0.3 rad/s; the jar moves at most 0.02 m/s.

The episode fails at once, checked after every physics substep, when: the jar tilts more than 15°, its centre slides
more than 30 mm horizontally from its start or rises more than 15 mm; the jar's or the lid's origin leaves the box
x -0.45 to 0.45 m, y -0.40 to 0.40 m, z 0.73 to 1.25 m, the worktop's footprint (|x| at most 0.45 m, |y| at most
0.58 m) or drops more than 5 mm below the worktop top (z = 0.75 m); the jar or the lid touches the floor; the lid
touches the worktop before stage 2; the lid's lowest point is more than 10 mm above the worktop top while its centre of
mass falls faster than 1.0 m/s, or faster than 0.3 m/s while the lid touches nothing; the lid leaves the thread
upward (more than 6 mm above its closed height while within 4 mm of the axis) at a turn whose remainder modulo a
quarter turn is outside 1.019 to 1.291 rad (lugs not in the gaps between the ramps); the parked left arm or left hand
touches the jar or the lid; or the physics becomes unstable. The step budget is 3,000 control steps (60 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (58 values for the Sharpa Wave hand, 54 for
the Wuji Hand 2.2), 1 to 3,000 rows, and a `hand` member that names the hand (an archive without it counts as
Sharpa Wave). After the agent's session, the verifier rebuilds the frozen scene with that hand in a fresh process of a
separate container without network and replays the rows once, open-loop. The replay stops at the first success or the
first failure, and later rows are not run. The task is passed if the replay ends in success; rows that run out first,
or the step budget reached first, leave it failed. Only the motor targets are read: no other member of the archive
changes the verdict.

A missing file scores 0, and so does a rejected one: larger than 64 MB, a row width that does not match the hand, a
non-finite value, no rows or too many, a target outside its actuator's range, or a `task` or `actuator_names` member
that does not match this task. A frozen scene that does not build to its recorded start is an infrastructure error,
not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

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
