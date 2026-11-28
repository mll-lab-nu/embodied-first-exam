# DexHand · Install a desk fan front guard (standard)

| | |
|---|---|
| Task ID | `dexhand-fan-guard-install-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
| Instance | `fan_guard_install`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Install the front guard on the desk fan.

## Success criteria
One final condition, checked at the end of each control step (50 Hz), must hold for 50 consecutive control steps
(1 s):
- Seated: the guard's origin is within 5 mm of the fan's axis and within 2.5 mm of the seated position along it, and
  the guard's axis is within 5° (0.0873 rad) of the fan's axis, dome facing out.
- Clipped: all four clips are closed (hinge angle at most 0.12 rad), the guard's rim lies inside each clip's U channel
  (between the fan's rear rim and the clip's lip along the axis, and between the lip's end and the clip's bridge
  radially), and each of the two upper clips has stayed closed since a control step at or after the one at which the
  guard was first seated (the lower clips may close earlier).
- Released: the hand touches neither the guard, a clip nor the fan, and the guard moves at most 0.02 m/s and turns
  at most 0.2 rad/s.

The episode fails at once, checked after every 2 ms physics substep, when: the fan moves more than 30 mm from its
start or tilts more than 0.1 rad; the guard's centre of mass is below the worktop top (z = 0.65 m) or leaves the box
x 0.20 to 1.10 m, y -0.55 to 0.55 m, z 0.60 to 1.40 m; once the guard's centre of mass has been more than 50 mm above
its start, the guard touches the worktop, a table leg or the floor; the guard touches nothing while its centre of mass
falls faster than 0.2 m/s; the guard touches the fan's base, stem, neck, motor housing, oscillation knob, feet or
speed buttons; or the physics becomes unstable. The step budget is 6,000 control steps (120 s).

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
