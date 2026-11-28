# DexHand · Place a two-handle pot into a shelf (standard)

| | |
|---|---|
| Task ID | `dexhand-pot-shelf-transfer-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
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

Graded is the live episode on the simulator service; nothing is replayed. The service runs the hand the runner
selects (Sharpa Wave unless the Wuji Hand 2.2 is selected; `spec()["hand"]` names it). The agent may reset up to
20 times, each reset starting a new episode from the same frozen start; only the last episode is graded. An
episode ends at the agent's `POST /finish`, when the agent's session ends (at the latest after 1 h), at the first
failure above (a score of 0), at the step budget where the task has one, or on a simulator error (a score of 0). A
success neither ends the episode nor is shown to the agent.

Each stage before the last counts at the moment it is completed. The last stage, with its full hold, must be met on
the state the episode ends in: every check goes on after it is first met, and a failure after it still scores 0. If
it is not met at `/finish` or at the session's end, the robot holds its current targets for up to 3 s of simulated
time, and the episode passes if the last stage completes within that time without a failure. At the step budget it
must be met at that step. Targets outside an actuator's range are clipped. Each episode's start is checked against
the frozen instance; a mismatch is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 6 GiB | 1024 | no GPU | — |
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
