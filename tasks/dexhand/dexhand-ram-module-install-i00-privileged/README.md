# DexHand · Install a desktop DDR4 RAM module (privileged)

| | |
|---|---|
| Task ID | `dexhand-ram-module-install-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | privileged |
| Instance | `ram_module_install`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Take the memory module out of its foam holder and install it in the motherboard's outer memory slot, the one nearest the
board edge, the right way round; press it in until the latch snaps shut, then let go.

## Success criteria
Positions in the socket are measured in the target socket's frame. Three stages, in this order, checked at the end of
each control step (50 Hz):
1. Picked: the module does not touch its foam holder, its lower edge (the module's origin) is at z = 0.851 m or
   higher, and the thumb and at least one other finger touch it.
2. Seated: both ends of the module's lower edge are 1.5 to 2.6 mm above the socket's base, at most 0.5 mm off the
   slot's centre line sideways; the module's centre is within 1.0 mm of the slot's centre along it; the module's
   height axis is within 3° of the socket's vertical, and its length axis within 3° of the socket's keyed direction
   (a reversed module never counts).
3. Latched: the module is seated as in stage 2 and the socket's latch is closed (hinge angle at most 0.08 rad).

Then, for 50 consecutive control steps (1 s): the module is seated and latched, the hand touches neither the module nor
the latch, and the module moves at most 0.01 m/s and turns at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: the module touches anything other than the
hand, its foam holder or the target socket (the bench, the tray, the motherboard and its components, the other
sockets, the floor); the module touches nothing while its centre of mass falls faster than 0.2 m/s, or falls more than
50 mm while touching nothing; a corner of the module is below the bench top (z = 0.825 m); within the target socket,
an end of the module's lower edge is less than 1.2 mm above the socket's base; the module's origin leaves the box
x 0.30 to 0.95 m, y -0.36 to 0.34 m, z 0.826 to 1.25 m; or the physics becomes unstable. The step budget is 3,000
control steps (60 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (28 values for the Sharpa Wave hand, 26 for
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
