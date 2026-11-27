# DexHand · Stir milk into a mug of coffee with a teaspoon (privileged)

| | |
|---|---|
| Task ID | `dexhand-coffee-stir-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `coffee_stir`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Mix the milk into the coffee: stir it six times with the teaspoon, then lay the spoon on the worktop beside the mug.

## Success criteria
Three stages, in this order, checked once per control step (50 Hz):
1. In the hand and in the coffee: the thumb and at least one other finger touch the spoon, and the bowl centre, the
   bowl tip and the bowl neck (23 mm either side of the centre along the spoon) are all between 4 mm and 64 mm (the
   coffee surface) above the mug base and within 50 mm of the mug axis.
2. Stirred: the bowl centre has turned at least six full revolutions about the mug's vertical axis (world frame, net
   signed angle). The angle grows only while the thumb and another finger touch the spoon, the bowl is in the coffee
   as in stage 1 and the bowl centre is at least 8 mm from the axis; a change of more than 0.785 rad in one control
   step is not counted, and the count restarts from zero whenever the bowl leaves the coffee before the six turns are
   complete.
3. Laid down, for 50 consecutive control steps (1 s): nothing of the hand touches the spoon; the spoon touches the
   worktop and does not touch the mug; the bowl centre and the handle end are both at least 0.10 m from the mug axis
   horizontally; the spoon's axis is within 15° of horizontal; spoon and mug each move at most 0.02 m/s and turn at
   most 0.5 rad/s.

The coffee is not simulated: it exerts no force, and only the bowl's revolutions in it are measured.

The episode fails at once, checked after every 2 ms physics substep, when: the mug tilts more than 10°, slides more
than 20 mm or rises more than 5 mm; the spoon touches the floor, or touches the worktop before stage 2 is complete;
the spoon touches neither the hand, the mug nor the worktop while its centre of mass falls faster than 0.2 m/s; the
mug touches the floor; the bowl centre, bowl tip, bowl neck or handle end is more than 3 mm below the worktop top
(z = 0.75 m), or the mug base more than 5 mm below it; the bowl centre or the handle end leaves the box x 0 to 0.96 m,
y -0.48 to 0.48 m, z 0.70 to 1.60 m; a fingertip is inside the mug radius below the coffee surface; an arm link or
the stand, or the parked left hand, touches the mug, the spoon, the worktop or the floor; or the physics becomes
unstable. The step budget is 3,000 control steps (60 s).

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
