# DexHand · Independent walnut rotation and selective release (privileged)

| | |
|---|---|
| Task ID | `dexhand-essential-two-object-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `essential_two_object`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Keep the wrist still. Holding walnut A in the fingers, turn it a quarter turn so that its top moves toward the
fingertips, turn it back, then drop only A so it comes to rest near the middle of the catch tray. Keep walnut B held in
the hand, unmoved and unturned, the whole time, and never let the two walnuts touch.

## Success criteria
The six wrist targets are locked at (-0.08, 0, 0.29, 0, 0, 0) (metres, then radians).
A trajectory with a row that changes any of them beyond float32 rounding is rejected.

Walnut poses are measured in the palm's frame, relative to their start. A contact counts when it carries more than 0.005
N; a finger touches a walnut when its links press it with more than 0.005 N in total. The speed is the fastest motion of
either walnut (m/s or rad/s). Every check below runs after each 2 ms physics substep (ten per control step). Three
stages, in this order, then a final hold. A control step counts toward a stage or the final hold only when its
conditions held at every substep of that step:
1. Turn A, for 5 consecutive control steps: A is within 0.16 rad of its start orientation turned 90° about the palm's
   across-palm axis (its top moving toward the fingertips), 1 to 5 fingers touch A, and the speed is below 0.25.
   While this stage is active, the episode fails if the hand stops touching A, A touches anything other than the
   hand, A moves more than 35 mm from its start place, or the speed exceeds 12.
2. Return A, for 5 consecutive control steps: A is within 0.16 rad of its start orientation, 1 to 5 fingers touch A,
   and the speed is below 0.25, with the same failures while active.
3. Release A, for 5 consecutive control steps: the hand does not touch A, A touches the catch tray's floor, and A is
   within 40 mm horizontally of the tray floor's centre.
4. Final hold, for 25 consecutive control steps: the stage 3 conditions, 1 to 5 fingers touch B, and the speed is
   below 0.06.

The episode fails at once when: any contact force on a walnut exceeds 80 N; the palm moves more than 3 mm or turns more
than 0.01 rad from its start; the walnuts touch each other; B moves more than 15 mm or turns more than 0.2 rad from its
start in the palm's frame, touches anything other than the hand, has no single hand contact above 0.005 N, or has no
finger touching it; A moves faster than 2.5 m/s or turns faster than 80 rad/s; A's centre is below z = 0.135 m or above
z = 0.6 m, or more than 0.1 m horizontally from the tray floor's centre; or the physics becomes unstable. There is no
step budget.

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
