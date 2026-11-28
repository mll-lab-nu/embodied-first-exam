# DexHand · Unfold a folding sweater dryer and stand it on its legs (privileged)

| | |
|---|---|
| Task ID | `dexhand-drying-rack-unfold-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `drying_rack_unfold`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Set up the folding sweater dryer on the kitchen counter with the dexterous hand.

## Success criteria
Three stages, in this order, checked at the end of each control step (50 Hz):
1. Unfolded: the hinge between the two halves is within 0.314 rad (18°) of flat, and each of the four leg hinges is
   open at least 1.571 rad (90°).
2. Standing: stage 1 holds, the rack tilts at most 10°, all four feet touch the counter top, and no other part of
   the rack touches it.
3. Released, for 50 consecutive control steps (1 s): the rack is standing as in stage 2, the hand does not touch it,
   and every part of the rack moves at most 0.02 m/s and turns at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: the centre of any collision shape of the
rack is below the counter top (z = 0.75 m), more than 0.90 m above it, or outside the counter's footprint (x -0.13 to
1.37 m, y -0.48 to 0.48 m); the rack touches the floor or the counter cabinet; the rack touches neither the counter
top nor the hand while its centre of mass falls faster than 0.05 m/s; once stage 2 has been reached, the rack tilts
more than 20°, the halves' hinge opens beyond 0.314 rad from flat or a leg closes below 1.571 rad; or the physics
becomes unstable. The step budget is 6,000 control steps (120 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (28 values for the Sharpa Wave hand, 26 for
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
