# DexHand · Carry a tray with two filled glasses around a bottle to the other counter (standard)

| | |
|---|---|
| Task ID | `dexhand-tray-glass-carry-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two dexterous hands, each on its own six-DoF actuated wrist stage, no arms: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `tray_glass_carry`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Carry the serving tray with the two filled glasses from the source counter to the receiving counter.

## Success criteria
The tray's position is the bottom centre of its floor. The receiving counter's target point is (0.78, 0.00) m, and its
tolerance is ±20 mm in x and ±30 mm in y. A glass is seated when its base is between 3 mm below and 8 mm above the tray
floor, in the tray's frame. Three stages, in this order, checked at the end of each control step (50 Hz):
1. Lifted: the tray touches neither counter, its base is at least 30 mm above the counter tops (z ≥ 0.91 m), and both
   glasses are seated.
2. Placed: the tray touches the receiving counter and not the source counter, its centre is within the target
   tolerance, it is tilted at most 5° and turned at most 10° about the vertical from its start, and both glasses are
   seated.
3. Released, held for 50 consecutive control steps (1 s): the placed conditions; no part of either hand touches the
   tray or a glass; both glasses are within 6° of vertical; and the tray and both glasses move at most 0.02 m/s and
   turn at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: a glass tilts more than 15° from vertical
(spilled); a glass base leaves its footprint ellipse on the tray (semi-axes 0.165 m and 0.23 m), rises more than 22 mm
above the tray floor or sinks more than 10 mm below it; the tray tilts more than 35°; the tray or a glass falls faster
than 0.6 m/s, or falls faster than 0.2 m/s while unsupported (the tray touching no hand and no counter, a glass
touching no hand, counter, tray or other glass); the steel bottle touches the tray, a glass or a hand; the tray touches
the source counter after stage 1; the tray touches the receiving counter while its centre is more than 40 mm (x) or
50 mm (y) from the target point; the tray or a glass touches the floor, has its origin more than 20 mm below the counter
tops (z = 0.88 m), or leaves the work box x 0 to 1.15 m, y -0.6 to 0.6 m, z 0.86 to 1.12 m; or the physics becomes
unstable. The step budget is 3,000 control steps (60 s).

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
