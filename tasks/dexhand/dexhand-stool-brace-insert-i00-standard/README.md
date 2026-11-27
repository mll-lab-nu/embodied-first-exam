# DexHand · Assemble a wooden stool cross brace (standard)

| | |
|---|---|
| Task ID | `dexhand-stool-brace-insert-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
| Instance | `stool_brace_insert`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Assemble the cross brace of a pine stool dry frame.

## Success criteria
A dowel end counts as seated in a bore when its tip is 12 to 19 mm past the bore's entry along the bore's axis, within
1.6 mm of that axis, and the dowel's axis is within 0.105 rad of the bore's. Four stages, in this order, checked at the
end of each control step (50 Hz; several may complete in the same step):
1. Brace lifted: the brace does not touch the table, its origin is at least 50 mm above its start, and the lowest
   corner of its bounding box is at least 20 mm above the table top (z = 0.76 m or higher).
2. Brace seated: one of the brace's dowels is seated in a bore of the lower side frame.
3. Frame lifted: the opposite (upper) side frame is lifted in the same sense as the brace in stage 1.
4. Assembled: every dowel end of the four rails (the brace included) is seated in exactly one bore, every bore of the
   two side frames holds exactly one dowel end, and every rail has one end in each side frame.

Then, for 50 consecutive control steps (1 s): the assembly of stage 4 holds, the hand touches no part, and every part
(both side frames and all four rails) moves at most 0.02 m/s and turns at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: the origin of a part is below the table top
(z = 0.74 m) or leaves the box x 0.23 to 1.23 m, y -0.73 to 1.03 m, z 0.70 to 1.60 m; the lower side frame moves more
than 30 mm from its start or tilts more than 10°; a rail that started seated tilts more than 10° or its seated dowel is
less than 8 mm deep in its bore; after stage 1, the brace's origin is less than 90 mm above the table top or the brace
touches the table; after stage 2, the brace tilts more than 20°; after stage 3, the upper frame is more than 20° from
upside down or touches the table; a part touches nothing while its centre of mass falls faster than 0.2 m/s; a part
touches the floor; or the physics becomes unstable. Tilts are measured between a part's long axis line and the
vertical. The step budget is 6,000 control steps (120 s).

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
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
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
