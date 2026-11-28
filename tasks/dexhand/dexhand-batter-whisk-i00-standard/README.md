# DexHand · Whisk batter in a bowl, drain and set the whisk down (standard)

| | |
|---|---|
| Task ID | `dexhand-batter-whisk-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `batter_whisk`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the balloon whisk, whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the
counter.

## Success criteria
The batter is not simulated. Whisking is measured on the head point, a point inside the whisk head 20 mm from the wire
tip along the whisk axis. The head point is in the batter when it is between 3 mm and 35.7 mm above the bowl's inner
floor origin, in the bowl's frame, and at least 4 mm inside the bowl's inner wall. "The robot" below means any part of
the arms, hands or stand. Five stages, in this order, checked at the end of each control step (50 Hz):
1. Picked up, for 10 consecutive control steps: the robot touches the whisk, the whisk touches neither the counter nor
   the bowl, and its lowest point is at least 30 mm above the counter top.
2. Immersed: the head point is in the batter.
3. Whisked: the head point has made at least 5 net revolutions about the bowl's axis during one continuous stay in the
   batter. Leaving the batter resets the count to zero. Steps with the head point less than 8 mm from the axis do not
   add to the count.
4. Drained, for 25 consecutive control steps: the robot touches the whisk, the wire tip is at least 10 mm above the
   bowl rim, the head point is within 55 mm of the bowl's axis, and the whisk hangs head-down with its axis within 30°
   of vertical.
5. Set down, held for 50 consecutive control steps (1 s): the whisk touches the counter top and touches neither the
   robot nor the bowl; its axis is within 30° of horizontal; its centre of mass is at least 0.12 m from the bowl's
   axis; and it moves at most 0.02 m/s and turns at most 0.3 rad/s.

The episode fails at once, checked at the end of each control step, when: the bowl tilts more than 10°, slides more
than 30 mm or lifts more than 20 mm from its start; the bowl or the whisk touches the floor, or its centre of mass is
below the counter top (z = 0.68 m) or outside the work box x 0.25 to 0.99 m, y -0.36 to 0.36 m, z 0.6 to 1.5 m; after
stage 1, the whisk touches nothing, its lowest point is more than 2 mm above the counter and it falls faster than
0.2 m/s; after stage 1 and before it is put on the counter, the whisk touches the counter, or goes more than 10
control steps in a row without robot contact. The whisk is put on the counter when, after stage 4, it first touches
the counter while the robot still touches it. After that, the episode fails if the whisk touches neither the robot nor
the counter for more than 5 control steps in a row. A physics warning in any substep also fails the episode. The step
budget is 4,000 control steps (80 s).

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
| `sim` | 2 | 7 GiB | 1024 | no GPU | — |
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
