# DexHand · Multi-turn encoder knob with fixed-wrist finger gait (privileged)

| | |
|---|---|
| Task ID | `dexhand-essential-rotary-gait-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `essential_rotary_gait`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Keep the wrist fixed and never let go of the knob. Turn the knob two full turns clockwise, as seen looking at its face
(which faces the thumb side), passing it from finger to finger at least four times, each new set of touching fingers
keeping one finger of the set before; then turn it one full turn back and hold it still.

## Success criteria
The six wrist targets are locked at (-0.08, 0, 0.29, 0, 0, 0) (metres, then radians).
A trajectory with a row that changes any of them beyond float32 rounding is rejected.

The knob's turn is its unwrapped hinge angle from the start, positive clockwise seen looking at its face. A finger
touches the knob when any of its links presses it with more than 0.005 N. A handoff is counted when the set of fingers
touching the knob has stayed the same for 0.04 s, differs from the previous such set and shares at least one finger with
it. Every check below runs after each 2 ms physics substep (ten per control step). Two stages, in this order, then a
final hold. A control step counts toward a stage or the final hold only when its conditions held at every substep of
that step:
1. Two turns forward, for 5 consecutive control steps: the turn is between 12.4464 and 12.6864 rad (4π ± 0.12), at
   least 4 handoffs have been counted, at least one finger touches the knob, and it turns slower than 0.25 rad/s.
2. One turn back, for 5 consecutive control steps: the turn is between 6.1632 and 6.4032 rad (2π ± 0.12), at least one
   finger touches the knob, and it turns slower than 0.25 rad/s.
3. Final hold, for 25 consecutive control steps: the turn is between 6.1632 and 6.4032 rad, at least one finger
   touches the knob, and it turns slower than 0.06 rad/s.

The episode fails at once when: any contact force on the knob exceeds 80 N; it turns faster than 12 rad/s; the palm
moves more than 3 mm or turns more than 0.01 rad from its start; no part of the hand touches the knob with more than
0.005 N; or the physics becomes unstable. There is no step budget.

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
