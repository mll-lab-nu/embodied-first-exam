# DexHand · Serve a pancake from a frying pan with a spatula (standard)

| | |
|---|---|
| Task ID | `dexhand-pancake-serve-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `pancake_serve`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Serve the pancake from the frying pan onto the plate with the kitchen turner (a spatula).

## Success criteria
Three stages, in this order, checked at the end of each control step (50 Hz, twenty 1 ms physics substeps):
1. On the blade, for 10 consecutive control steps: the pancake touches the turner's blade and nothing but the turner,
   it is at least 15 mm above its start height, and it tilts at most 30°.
2. Over the plate: still touching the blade and nothing but the turner, the pancake's centre is within 58 mm of the
   plate's centre horizontally and more than 6 mm above the plate's origin.
3. Served, for 50 consecutive control steps (1 s): the pancake touches the plate and nothing else; its centre is
   within 58 mm of the plate's centre horizontally; it tilts at most 20°; it moves at most 0.02 m/s and turns at most
   0.3 rad/s; the turner does not touch it, and every corner and the tip of the turner's blade is more than 80 mm from
   the pancake's centre horizontally (10 mm beyond its rim).

The episode fails at once, checked after every physics substep, when: the pancake touches nothing while its centre of
mass falls faster than 0.35 m/s; the turner does not touch the robot while its centre of mass falls faster than
0.35 m/s; the pancake touches the counter top or the floor; any part of the robot touches the pancake; the turner
touches the floor; the pancake's or the turner's origin is below the counter top (z = 0.85 m); the pan or the plate
moves more than 30 mm from its start or tilts more than 15°; the pancake, the pan, the plate or the turner leaves the
box x 0.23 to 1.13 m, y -0.65 to 0.45 m, z 0.80 to 1.50 m; or the physics becomes unstable. The step budget is
3,000 control steps (60 s).

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
