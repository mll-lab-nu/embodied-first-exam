# DexHand · Operate a manual coffee grinder (privileged)

| | |
|---|---|
| Task ID | `dexhand-grinder-crank-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `grinder_crank`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hold the coffee grinder steady with one hand, turn its crank by the knob two full turns clockwise (seen from above) with
the other, then let go of the grinder.

## Success criteria
Two stages, in this order, checked at the end of each control step (50 Hz):
1. Turned: the crank has turned at least two full turns (4π rad) clockwise, seen from above, relative to the grinder
   body, net of any turning back (the crank hinge's angle from its start).
2. Released, for 50 consecutive control steps (1 s): the crank is still at least two net turns from its start; no
   part of either hand touches the grinder (body, crank or knob); the grinder's base touches the counter; the grinder
   tilts at most 10°; it moves at most 0.02 m/s and turns at most 0.2 rad/s; the crank turns at most 0.5 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: any stand, torso or arm link of the robot
(anything but the two hands) touches anything; the grinder's origin is more than 5 mm below the counter top
(z = 0.70 m); the grinder's axis tilts more than 10° from vertical; its origin moves more than 20 mm horizontally from
its start or rises more than 20 mm; the grinder body turns more than 45° about its own axis; the crank is more than 90°
net counter-clockwise from its start; or the physics becomes unstable. The step budget is 3,000 control steps (60 s).

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
