# DexHand · Sweep debris into a held dustpan (privileged)

| | |
|---|---|
| Task ID | `dexhand-sweep-dustpan-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `sweep_dustpan`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan.

## Success criteria
Here a control step is one 0.5 ms physics step (2,000 Hz), and every check below runs after each one. The right hand
starts holding the broom and the left hand the dustpan. A contact counts only when it carries at least 0.001 N. A
piece is brushed once any of the broom's bristles has touched it. A piece is in the pan when its whole collision shape
lies inside the pan floor's volume, in the pan's frame (within 1 mm of the floor's side edges, at most 131 mm forward
or back of its centre, and no higher than 0.11 m), and it touches the pan's floor, lip, back or a side. Success needs
one condition, held for 2,000 consecutive physics steps (1 s):
- all six pieces have been brushed;
- all six pieces are in the pan;
- the pan's origin is at least 0.05 m above the floor;
- every piece moves slower than 0.03 m/s and turns slower than 0.8 rad/s;
- the first 1.2 s of the episode (the settling period) are over.

The episode fails at once when: a piece's centre leaves the floor work area (x 0.45 to 1.0 m, y -0.5 to 0.4 m, from
10 mm below to 0.25 m above the floor); any part of the robot touches a piece; two parts of the robot touch each other,
other than two parts of the same hand; a part of the robot other than a tool's own hand presses that tool with more
than 0.01 N; after the settling period, fewer than two parts of a tool's hand touch its shaft with at least 0.01 N
each (the tool dropped), or a tool slips in its hand by 25 mm or more, or turns in it by 0.25 rad or more, from where it
sat at the end of the settling period; or the physics becomes unstable. The step budget is 160,000 physics steps
(80 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (58 values for the Sharpa Wave hand, 54 for
the Wuji Hand 2.2), 1 to 160,000 rows, and a `hand` member that names the hand (an archive without it counts as
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
