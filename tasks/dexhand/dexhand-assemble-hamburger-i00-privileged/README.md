# DexHand · Assemble a neatly aligned hamburger (privileged)

| | |
|---|---|
| Task ID | `dexhand-assemble-hamburger-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `assemble_hamburger`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Build a hamburger on the serving plate, every layer upright and centred over the plate.

## Success criteria
The six layers are the bottom bun, patty, cheese, tomato, lettuce and top bun, in that order from the bottom. The cheese
and the lettuce each have two hinged side wings. There are no stages. Success needs one condition, held for 100
consecutive control steps (2 s), checked at the end of each control step (50 Hz):
- the centre of every layer is within 12 mm, horizontally, of the plate centre (x = -0.16 m, y = 0);
- the layer centres rise in recipe order, and each layer touches the next one up;
- the bottom bun touches the plate;
- no part of the hand touches any layer;
- every layer is tilted at most 0.22 rad (12.6°) from level;
- every part of every layer moves at most 0.025 m/s and turns at most 0.25 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: any part of a layer has its origin below
the table top (z = 0.3 m) or outside the work box x -0.64 to 0.64 m, y -0.52 to 0.52 m, z 0.3 to 0.8 m; any layer
touches the table top or the floor; a wing of the cheese or the lettuce bends more than 0.65 rad; or the physics
becomes unstable. The step budget is 7,500 control steps (150 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (28 values for the Sharpa Wave hand, 26 for
the Wuji Hand 2.2), 1 to 7,500 rows, and a `hand` member that names the hand (an archive without it counts as
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
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
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
