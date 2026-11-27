# DexHand · Free-held cube layer reversal (privileged)

| | |
|---|---|
| Task ID | `dexhand-essential-cube-layer-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `essential_cube_layer`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Keep the wrist locked and hold the cube body steady with your other fingers. Turn only the top layer a quarter turn
counter-clockwise, as seen from above, then back to where it started, then a quarter turn counter-clockwise again, and
hold it still.

## Success criteria
The six wrist targets are locked at (-0.08, 0, 0.29, 0, 0, 0) (metres, then radians).
A trajectory with a row that changes any of them beyond float32 rounding is rejected.

The top layer's turn is its hinge angle relative to the cube's body, positive counter-clockwise seen from above. A
finger counts as touching a part when any of its links presses it with at least 0.005 N. Every check below runs after
each 2 ms physics substep (ten per control step). Three stages, in this order, then a final hold. A control step counts
toward a stage or the final hold only when its conditions held at every substep of that step:
1. Quarter turn, for 5 consecutive control steps: the turn is between 1.4508 and 1.6908 rad (π/2 ± 0.12), at least
   one finger touches the body and at least one touches the top layer.
2. Back to zero, for 5 consecutive control steps: the turn is within ±0.12 rad, with the same finger contacts.
3. Quarter turn again, for 5 consecutive control steps: as in stage 1.
4. Final hold, for 15 consecutive control steps: the turn is between 1.4508 and 1.6908 rad, at least one finger
   touches the body, and no part of the cube moves faster than 0.12 (m/s or rad/s).

The episode fails at once when: any contact force on the cube exceeds 80 N; any part of the cube moves faster than 20
(m/s or rad/s); the palm moves more than 6 mm or turns more than 0.035 rad from its start; the cube touches anything
other than the hand with more than 0.01 N; the cube's body moves more than 20 mm or turns more than 0.35 rad from its
start; or the physics becomes unstable. There is no step budget.

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (28 values for the Sharpa Wave hand, 26 for
the Wuji Hand 2.2), 1 to 50,000 rows, and a `hand` member that names the hand (an archive without it counts as
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
