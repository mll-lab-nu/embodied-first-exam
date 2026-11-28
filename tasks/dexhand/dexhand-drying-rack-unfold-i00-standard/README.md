# DexHand · Unfold a folding sweater dryer and stand it on its legs (standard)

| | |
|---|---|
| Task ID | `dexhand-drying-rack-unfold-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
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
