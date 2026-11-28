# DexHand · Assemble a neatly aligned hamburger (standard)

| | |
|---|---|
| Task ID | `dexhand-assemble-hamburger-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
| Instance | `assemble_hamburger`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Build a hamburger on the serving plate, every layer upright and centred over the plate.

## Success criteria
The six layers are the bottom bun, patty, cheese, tomato, lettuce and top bun, in that order from the bottom. The cheese
and the lettuce each have two hinged side wings. There are no stages. Success needs one condition, held for 100
consecutive control steps (2 s), checked at the end of each control step (50 Hz):
- the centre of every layer is within 12 mm, horizontally, of the plate centre (x = -0.16 m, y = 0);
- the layer centres rise in recipe order, and each layer touches the next one up;
- the bottom bun touches the plate;
- no part of the hand touches any layer;
- every layer is tilted at most 0.22 rad (12.6°) from level;
- every part of every layer moves at most 0.025 m/s and turns at most 0.25 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: any part of a layer has its origin below
the table top (z = 0.3 m) or outside the work box x -0.64 to 0.64 m, y -0.52 to 0.52 m, z 0.3 to 0.8 m; any layer
touches the table top or the floor; a wing of the cheese or the lettuce bends more than 0.65 rad; or the physics
becomes unstable. The step budget is 7,500 control steps (150 s).

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
