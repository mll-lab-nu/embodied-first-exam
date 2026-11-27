# AutoBio · pipette (privileged)

| | |
|---|---|
| Task ID | `autobio-pipette-i00-privileged` |
| Benchmark | [AutoBio](https://github.com/autobio-bench/AutoBio) (Lan et al., 2025), upstream `autobio-bench/AutoBio@0850421` |
| Robot | Two UR5e arms: one with a DexHand021 hand that holds a pipette, one with a Robotiq 2F-85 gripper |
| Mode | privileged |
| Instance | `pipette`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Draw up liquid from the 50 mL tube with the pipette: press the plunger, push the tip down into the liquid near the
middle of the tube, let the plunger go, then lift the tip well out of the tube.

## Success criteria
Three steps, in this order; the first two are latched once they happen:
1. Dip: the pipette's tip is within 6.5 mm horizontally of the tube's axis (its body origin), more than 5 mm below the
   liquid's surface, and the plunger thumb's command (the position target, not the joint's position) is above 0.70 rad.
2. Release: the tip is below the liquid's surface and the thumb's command is below 0.45 rad.
3. Lift: the tip is more than 0.05 m higher than the liquid's surface.
The first control step at which step 3 holds after steps 1 and 2 ends the replay as a success.

The verifier replays `/app/output/trajectory.npz` (array `actions`, shape (T, n) with n the robot's controlled
actuators, 1 ≤ T ≤ 600,000, finite values) once, open-loop, in a fresh process in a separate sandbox without network,
from its own copy of the frozen instance. Each row is one control step of 2 ms (one physics step), with one position
target per actuator, clipped to the actuators' ranges. AutoBio's `check()` is evaluated after every control step. A
MuJoCo physics warning (an unstable state) ends the replay at once as a failure; the renderer's own warning
(`VGEOMFULL`) does not count. A replay that reaches 600,000 control steps ends there.

A missing file scores 0, and so does an invalid one: not a readable `.npz`, no `actions` array, a `task` entry that
names another task, the wrong shape, a non-finite value, or more than 600,000 rows. A replay that gives no result, and
a replay whose model or start state does not match the instance's recorded hashes, are infrastructure failures, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 8192 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
AutoBio ([autobio-bench/AutoBio](https://github.com/autobio-bench/AutoBio) @ `0850421`) states **no licence** for its
code or its own assets (the digitized instruments, tubes, racks and pipette, and two binaries without source: the
thread and detent MuJoCo plugins `libmjlab.so.3.3.0` and the liquid-surface solver `meshplane.so`). No file of AutoBio
is in this repository, and the simulator image is built locally and never published; it is used here for research
evaluation only. The robot models AutoBio bundles keep their own licences: UR5e and Robotiq 2F-85 (BSD), ALOHA 2
(BSD), DexHand021 (Apache-2.0); the display font is under the SIL OFL. The simulator is MuJoCo 3.3.0 (Apache License
2.0). Details: `images/autobio/BUILD_ONLY`.
