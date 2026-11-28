# DexHand · Hang a large picture on two wall hooks (standard)

| | |
|---|---|
| Task ID | `dexhand-picture-hang-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | standard |
| Instance | `picture_hang`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hang the framed picture on the two wall hooks.

## Success criteria
Three stages, in this order, checked at the end of each control step (50 Hz):
1. Lifted: the frame's origin is at least 20 mm above its start height (z = 0.74 m or higher) and the frame does not
   touch the console.
2. Engaged: each D-ring on the frame's back is threaded on its own hook (the hook's load saddle lies inside the ring's
   D-shaped loop, within 0.5 mm) and touches it.
3. Hanging, for 50 consecutive control steps (1 s): both rings are threaded on and touching their hooks; each hook
   carries at least 20 % of the frame's weight through its ring (vertical contact force) and the two together at least
   85 %; no hand touches the frame or the rings; the frame touches neither the console nor the floor; it rolls at most
   3° and tilts at most 0.1 rad from upright; its centre of mass moves at most 0.02 m/s and it turns at most
   0.15 rad/s. Contact with the wall is allowed.

The episode fails at once, checked after every 2 ms physics substep and at the end of every control step, when: a
stand, torso or arm link of the robot touches anything (only the hands may make contact); the frame or a ring touches
the floor; the frame's origin leaves the box x 0.20 to 0.76 m, y -0.45 to 0.45 m, z 0.60 to 1.30 m; the frame tilts
more than 0.6 rad; after stage 1, the frame's origin is more than 10 mm below its start height; after stage 2, no
hand touches the frame and the two rings are not both threaded; after stage 1, the frame is supported by nothing (no
hand touches it, it does not touch the console, and the two rings are not both threaded on and touching their hooks):
at the end of a control step this fails at once, within a control step only while its centre of mass falls faster
than 0.2 m/s; or the physics becomes unstable. The step budget is 3,000 control steps (60 s).

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
