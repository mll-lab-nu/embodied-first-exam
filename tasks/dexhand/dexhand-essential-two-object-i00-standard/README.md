# DexHand · Independent walnut rotation and selective release (standard)

| | |
|---|---|
| Task ID | `dexhand-essential-two-object-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
| Instance | `essential_two_object`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Keep the wrist still. Holding walnut A in the fingers, turn it a quarter turn so that its top moves toward the
fingertips, turn it back, then drop only A so it comes to rest near the middle of the catch tray. Keep walnut B held in
the hand, unmoved and unturned, the whole time, and never let the two walnuts touch.

## Success criteria
The six wrist targets are locked at (-0.08, 0, 0.29, 0, 0, 0) (metres, then radians).
A request with a row that changes any of them beyond float32 rounding is refused with an error at that row; the rows before it in the same request have already run.

Walnut poses are measured in the palm's frame, relative to their start. A contact counts when it carries more than 0.005
N; a finger touches a walnut when its links press it with more than 0.005 N in total. The speed is the fastest motion of
either walnut (m/s or rad/s). Every check below runs after each 2 ms physics substep (ten per control step). Three
stages, in this order, then a final hold. A control step counts toward a stage or the final hold only when its
conditions held at every substep of that step:
1. Turn A, for 5 consecutive control steps: A is within 0.16 rad of its start orientation turned 90° about the palm's
   across-palm axis (its top moving toward the fingertips), 1 to 5 fingers touch A, and the speed is below 0.25.
   While this stage is active, the episode fails if the hand stops touching A, A touches anything other than the
   hand, A moves more than 35 mm from its start place, or the speed exceeds 12.
2. Return A, for 5 consecutive control steps: A is within 0.16 rad of its start orientation, 1 to 5 fingers touch A,
   and the speed is below 0.25, with the same failures while active.
3. Release A, for 5 consecutive control steps: the hand does not touch A, A touches the catch tray's floor, and A is
   within 40 mm horizontally of the tray floor's centre.
4. Final hold, for 25 consecutive control steps: the stage 3 conditions, 1 to 5 fingers touch B, and the speed is
   below 0.06.

The episode fails at once when: any contact force on a walnut exceeds 80 N; the palm moves more than 3 mm or turns more
than 0.01 rad from its start; the walnuts touch each other; B moves more than 15 mm or turns more than 0.2 rad from its
start in the palm's frame, touches anything other than the hand, has no single hand contact above 0.005 N, or has no
finger touching it; A moves faster than 2.5 m/s or turns faster than 80 rad/s; A's centre is below z = 0.135 m or above
z = 0.6 m, or more than 0.1 m horizontally from the tray floor's centre; or the physics becomes unstable. There is no
step budget.

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
