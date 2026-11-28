# DexHand · Remove and reinstall a vacuum dust bin (privileged)

| | |
|---|---|
| Task ID | `dexhand-vacuum-bin-reseat-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two dexterous hands, each on its own six-DoF actuated wrist stage, no arms: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `vacuum_bin_reseat`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Remove the dust bin from the handheld vacuum on the counter and reinstall it.

## Success criteria
Positions of the bin are measured in the vacuum body's frame, relative to the bin's seated pose. Three stages, in this
order, checked at the end of each control step (50 Hz, twenty 1 ms physics substeps):
1. Removed: the release button has been pressed down at least 5.8 mm at a moment when the bin's origin was within
   5 mm of its seated position (tracked after every physics substep), and afterwards the bin's origin is more than
   30 mm from its seated position.
2. Reseated: the bin's origin is within 3 mm and its orientation within 0.05 rad of the seated pose, the button is
   back up (at most 1.5 mm pressed), and the bin's catch is behind the latch tooth's face (at most 0.5 mm in front of
   it). Whenever this no longer holds, stage 2 has to be reached again.
3. Final hold, for 50 consecutive control steps (1 s): stage 2 holds; no part of the robot touches the bin, the vacuum
   body or the button; the bin moves at most 0.01 m/s and turns at most 0.1 rad/s; the vacuum body moves at most
   0.01 m/s.

The episode fails at once, checked after every physics substep, when: the vacuum body moves more than 50 mm from its
start or tilts more than 0.35 rad; the bin's origin goes below the counter top (z = 0.65 m) or leaves the box x 0.20
to 1.10 m, y -0.45 to 0.45 m, z 0.60 to 1.20 m; the bin's centre of mass falls faster than 0.99 m/s, or faster than
0.55 m/s while the bin touches nothing; the bin touches the floor or a table leg; a contact between the bin and the
vacuum body or button penetrates more than 4 mm; or the physics becomes unstable. The step budget is 3,000 control
steps (60 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (56 values for the Sharpa Wave hand, 52 for
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
| `main` (the agent's) | 2 | 7 GiB | 2048 | no GPU | 10 GiB |
| verifier (as `main`) | 2 | 7 GiB | no cap | no GPU | 10 GiB |

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
