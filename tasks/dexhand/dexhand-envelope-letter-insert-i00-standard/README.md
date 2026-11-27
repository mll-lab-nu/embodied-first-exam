# DexHand · Put a folded letter into an envelope (standard)

| | |
|---|---|
| Task ID | `dexhand-envelope-letter-insert-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `envelope_letter_insert`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the folded letter into the envelope.

## Success criteria
The letter's corners are taken on its mid-plane and measured in the envelope's frame. "Inside the seams" means within
the pocket's width between the two side seams (107 mm either side of the centre line, 0.6 mm tolerance); "between the
walls" means the letter's mid-plane lies inside the 4 mm gap between the envelope's back and front walls, allowing
for the letter's 2 mm thickness (0.6 mm tolerance). Three stages, in this order, checked at the end of each control
step (50 Hz):
1. At the mouth: the two leading corners are at least 10 mm past the mouth line, inside the seams and between the
   walls, while the two trailing corners are still outside the mouth line.
2. Inserted: the outermost corner is at most 4.95 mm (5 % of the letter's length) beyond the mouth line, and all four
   corners are inside the seams, in front of the bottom seam and between the walls.
3. Released, for 50 consecutive control steps (1 s): stage 2 holds, the hand touches neither the letter nor the
   envelope, and both move at most 0.01 m/s and turn at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: the letter's or the envelope's origin is
more than 2 mm below the desk top (z = 0.70 m), more than 0.30 m above it, or outside the desk's footprint (x 0.18 to
0.78 m, y -0.40 to 0.40 m); the envelope moves more than 50 mm horizontally from its start or tilts more than
0.35 rad; the letter or the envelope touches the floor; the letter and the envelope interpenetrate by more than
0.7 mm; a point of the letter's mid-plane lies inside the envelope's back wall, front wall, a side seam, the bottom
seam or the mouth lip; the robot's arm, stand or parked left hand touches the letter or the envelope; the letter or the
envelope touches nothing while its centre of mass falls faster than 0.1 m/s; or the physics becomes unstable. The step
budget is 6,000 control steps (120 s).

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
