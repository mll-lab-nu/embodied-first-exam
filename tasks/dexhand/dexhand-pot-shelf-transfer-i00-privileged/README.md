# DexHand · Place a two-handle pot into a shelf (privileged)

| | |
|---|---|
| Task ID | `dexhand-pot-shelf-transfer-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `pot_shelf_transfer`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Lift the pot by its two handles with both hands, carry it into the shelf on the left and set it down upright on the
shelf board at the target, then open both hands and move them away.

## Success criteria
Here a control step is one 2 ms physics step (500 Hz), and every check below runs after each one. The pot's position is
the centre of its base. A contact carries load when its normal force is at least 0.02 N. Two stages, in this order:
1. Lifted, for 250 physics steps (0.5 s) in total, not necessarily in a row: the pot's base is above z = 0.785 m; no
   loaded contact joins the pot to the worktop or the shelf board; and each hand pushes the pot upward with at least
   0.5 N.
2. Placed, held for 1,000 consecutive physics steps (2 s): the pot's base is within 40 mm horizontally of the target
   (0.46, 0.31) m and within 12 mm of its height (z = 0.79 m); the pot is tilted at most 0.1 rad; it moves at most
   0.03 m/s and turns at most 0.15 rad/s; the vessel (radius 0.143 m) lies within the shelf board's outline; the pot has
   a loaded contact with the shelf board and touches nothing else; the pot's collision shape lies inside the shelf
   compartment (between the side walls, from 50 mm in front of the board's front edge to the back wall, below the
   shelf top, and no lower than 12 mm below the board top); and no part of either hand is within 40 mm of the pot.

The episode fails at once when: the pot's base falls below z = 0.7 m or leaves the work box x -0.1 to 1.1 m, y -0.5
to 0.85 m, z 0.7 to 1.45 m; the pot tilts more than 0.5 rad; the pot touches nothing for more than 30 physics steps in
a row, or falls faster than 0.6 m/s; with load, the pot touches anything other than the two hands, the worktop and the
shelf board, or any robot part other than a hand; with load, a robot part touches the furniture, the floor or another
robot part, other than two parts of the same hand; a hand presses more than 3 mm into the pot; any joint passes its
range by more than 0.005 rad; or the physics becomes unstable. The step budget is 30,000 physics steps (60 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (58 values for the Sharpa Wave hand, 54 for
the Wuji Hand 2.2), 1 to 30,000 rows, and a `hand` member that names the hand (an archive without it counts as
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
| `main` (the agent's) | 2 | 9 GiB | 1024 | no GPU | 10 GiB |
| verifier (as `main`) | 2 | 9 GiB | no cap | no GPU | 10 GiB |

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
