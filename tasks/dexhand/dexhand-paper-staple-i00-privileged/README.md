# DexHand · Align and staple three paper sheets (privileged)

| | |
|---|---|
| Task ID | `dexhand-paper-staple-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `paper_staple`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Square up the 3 loose A5 sheets and staple them together at a corner with the desk stapler, then let go.

## Success criteria
The sheets are numbered from the bottom one up. Four stages, in this order, checked at the end of each control step
(50 Hz); each later stage also needs the conditions of stages 1 and 2 at the same step:
1. Aligned: every corner of sheets 2 and 3 is within 2 mm of the matching corner of sheet 1 (in sheet 1's plane);
   each sheet lies 0.25 to 1.5 mm (0.5 to 3 sheet thicknesses) above the one below it along sheet 1's normal; sheets
   1 and 2, and sheets 2 and 3, touch.
2. In the throat: the stapler's staple point (on its anvil, under the driver blade) lies inside every sheet, 3 to
   30 mm from both edges at one corner of it, and every sheet's mid-plane is 0 to 6 mm above that point.
3. Pressed: the head's hinge is within 0.01 rad of its bottom stop and the driver blade touches the top sheet.
4. Released, for 50 consecutive control steps (1 s): the head's hinge is back up (at most 0.02 rad), no part of the
   robot touches a sheet or the stapler, and every sheet moves at most 0.02 m/s.

The episode fails at once, checked after every 2 ms physics substep, when: a sheet's origin is more than 1 mm below its
resting height on the desk top (z = 0.78 m), leaves the desk's footprint (x 0.25 to 0.99 m, y -0.36 to 0.36 m) or the
box x 0.20 to 1.10 m, y -0.45 to 0.45 m, z 0.70 to 1.20 m, or a sheet's corner is more than 15 mm below the desk top;
the stapler's base moves more than 30 mm horizontally from its start or tilts more than 0.26 rad; a sheet or the
stapler's base falls faster than 0.2 m/s while touching nothing; an arm link or the stand touches anything but the
robot itself; a sheet or the stapler touches the floor or a desk leg; or the physics becomes unstable. The step budget
is 6,000 control steps (120 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (58 values for the Sharpa Wave hand, 54 for
the Wuji Hand 2.2), 1 to 6,000 rows, and a `hand` member that names the hand (an archive without it counts as
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
