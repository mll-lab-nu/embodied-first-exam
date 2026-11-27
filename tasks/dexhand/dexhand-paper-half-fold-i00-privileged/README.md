# DexHand · Fold a sheet of paper in half with a permanent crease (privileged)

| | |
|---|---|
| Task ID | `dexhand-paper-half-fold-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `paper_half_fold`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the
marked center line, take the hand away, and leave the folded sheet lying on the table.

## Success criteria
The sheet is simulated as a 9 × 5 grid of points (vertices) with elastic and plastic bending. Its left half is fixed.
The fold angle is the angle of the line from the centre line to the free edge, measured up from the table: flat is 0,
folded fully over is π rad. The crease is the permanent (plastic) bend of the hinges on the centre line. Stretch is
the largest relative change in length of any edge of the sheet so far in the episode. There are no stages. Success
needs one condition, held for 100 consecutive control steps (2 s), checked at the end of each control step (50 Hz):
- the fold angle is above 2.6 rad;
- the free edge is within 18 mm of the fixed edge (mean distance between matching points);
- the crease is above 2.2 rad on average, and at least 90% of the centre-line hinges are above 2.2 rad;
- no part of the hand touches the paper;
- the stretch is below 8%;
- every vertex is over the table top (x from -0.345 to 0.135 m, y from -0.30 to 0.30 m) and at most 2 mm below it
  (z ≥ 0.298 m).

The episode fails at once, checked after every 0.5 ms physics substep (40 per control step), when: any vertex is more
than 10 mm below the table top (z < 0.29 m); any vertex leaves the work box x -0.03 to 0.19 m, y -0.09 to 0.09 m,
z ≤ 0.45 m; the stretch exceeds 8%; or the physics becomes unstable. The step budget is 1,500 control steps (30 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (28 values for the Sharpa Wave hand, 26 for
the Wuji Hand 2.2), 1 to 1,500 rows, and a `hand` member that names the hand (an archive without it counts as
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
