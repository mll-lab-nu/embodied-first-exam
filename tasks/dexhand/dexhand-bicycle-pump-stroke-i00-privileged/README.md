# DexHand · Inflate a tire with a portable bicycle pump (privileged)

| | |
|---|---|
| Task ID | `dexhand-bicycle-pump-stroke-i00-privileged` |
| Benchmark | [DexHand](https://www.embodied-first-exam.ai/suite/dexhand/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Tianji Marvin fixed stand with two 7-joint arms and a dexterous hand on each wrist: Sharpa Wave (22 finger actuators each) by default, or Wuji Hand 2.2 (20 each) |
| Mode | privileged |
| Instance | `bicycle_pump_stroke`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pump up the bicycle tire: push the pump's hose head onto the valve and close its lock, pump the handle 28 full strokes,
then open the lock, pull the head off and let go of the pump.

## Success criteria
Piston depth is how far the handle is pushed down from its top position (full travel 0.20 m). Air and the tyre are not
simulated: the gauge reading is a count of strokes. The head is connected when its slide is within 0.5 mm of its seat
on the valve stem and its thumb lock lever is at 1.5 rad or more (closed is 1.65 rad). Stages, in this order:
1. Connected: the head is connected once. This is checked after every 2 ms physics substep.
2. Strokes: 28 strokes are counted. A stroke counts when the handle reaches a depth of at least 0.18 m and later comes
   back to a depth of at most 0.04 m, with the head connected at every substep in between. A substep with the head
   not connected cancels the stroke in progress. Shallower strokes do not count and are not failures.
3. Disconnected: after the 28 strokes, the lock lever is opened to 0.5 rad or less while the head is at least 12.5 mm
   back from its seat. This is checked after every substep.
4. Released, held for 50 consecutive control steps (1 s), checked at the end of each control step (50 Hz): the
   handle depth is at most 10 mm; no part of the robot touches the pump or its head; the pump is tilted at most 5°;
   and the pump body and the handle each move at most 0.02 m/s.

The episode fails at once, checked after every 2 ms physics substep, when: after the head is first connected and
before the 28 strokes, the head moves more than 2 mm back from its seat or the lock lever drops below 1.2 rad; after
the 28 strokes, the head is more than 2 mm back from its seat while the lever is at 1.2 rad or more; the pump tilts
more than 15°, its base moves more than 30 mm sideways or rises more than 20 mm from its start; the pump's centre of
mass is below the bench top (z = 0.7 m) or any part of the pump touches the floor; or the physics becomes unstable.
The step budget is 5,000 control steps (100 s).

The graded file is `/app/output/trajectory.npz`, as `s.save_trajectory` writes it: a finite numeric `actions` array
with one row of motor targets per control step (58 values for the Sharpa Wave hand, 54 for
the Wuji Hand 2.2), 1 to 5,000 rows, and a `hand` member that names the hand (an archive without it counts as
Sharpa Wave). After the agent's session, the verifier rebuilds the frozen scene with that hand in a fresh process of a
separate container without network and replays the rows once, open-loop. The replay stops at the first success or the
first failure, and later rows are not run. The task is passed if the replay ends in success; rows that run out first,
or the step budget reached first, leave it failed. Only the motor targets are read: no other member of the archive
changes the verdict.

A missing file scores 0, and so does a rejected one: larger than 64 MB, a row width that does not match the hand, a
non-finite value, no rows or too many, a target outside its actuator's range, or a `task` or `actuator_names` member
that does not match this task. A frozen scene that does not build to its recorded start is an infrastructure error,
not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
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
