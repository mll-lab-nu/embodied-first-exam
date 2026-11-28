# DexHand · Load two punched pages into a ring binder (standard)

| | |
|---|---|
| Task ID | `dexhand-binder-page-load-i00-standard` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | A dexterous right hand on a six-DoF actuated wrist stage, no arm: Sharpa Wave (22 finger actuators) by default, or Wuji Hand 2.2 (20) |
| Mode | standard |
| Instance | `binder_page_load`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Open the rings of the ring binder on the desk, thread both punched pages onto them through their holes, close the rings
and let go.

## Success criteria
Each page has three punched holes, one per ring. Four stages, in this order, checked at the end of each control step
(50 Hz):
1. Rings open: both toggle plates of the ring mechanism are at least 0.5 rad open.
2. Pages placed: the rings are open; each of the six holes is threaded by the right half of its own ring exactly once
   (the wire's centre line passes through the hole, within 3.5 mm of its centre) and not by the left half; the hand
   touches neither page; each page rests on the binder or on the other page; and each page's centre lies over the
   back cover.
3. Rings closed: both toggle plates are at most 0.05 rad open, every hole is linked exactly once by its closed ring,
   and both pages lie over the back cover.
4. Final hold, for 50 consecutive control steps (1 s): stage 3 holds, the hand touches neither page nor the binder,
   both pages rest on the binder or on each other, and each page stays within 2 mm and 0.03 rad of its pose at the
   start of the hold.

The episode fails at once, checked after every 2 ms physics substep, when: a page's origin is more than 2 mm below the
desk top (z = 0.70 m) or leaves the box x 0.20 to 0.98 m, y -0.38 to 0.48 m, z 0.698 to 1.10 m; the binder moves more
than 30 mm horizontally from its start or tilts more than 0.35 rad; a page touches the floor; a part of the hand
penetrates a page by more than 3 mm, or a ring wire by more than 1.2 mm (a ring may enter a page only through its
hole); a page touches nothing while it falls faster than 0.2 m/s and no ring half passes through any of its holes; or
the physics becomes unstable. The step budget is 6,000 control steps (120 s).

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
