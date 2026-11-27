# Embodied Olympics · shot put (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-shot-put-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `shot_put`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Put the shot from the circle so that it lands inside the sector at least 6 m out, then leave the circle from its back
half and stand.

## Success criteria
The robot stands in the rear half of a throwing circle (2.135 m across inside its rim, a stop board at the front),
facing a 34.92-degree sector, with a 7.26 kg shot resting on its open right palm against its neck. The hands have no
grip. The referee's stages, in order: release, landing, exit.
- Release: the right hand's last contact with the shot before a break of at least 0.03 s (shorter breaks count as
  still holding). At that moment the shot touches no part of the robot, and it is moving away from the right shoulder
  joint with at least half of its speed relative to that joint (a push, not a throw or a sling). Until the release,
  the shot's centre never goes below or behind the line of the shoulders, and nothing but the right hand and the
  trunk touches it.
- Landing: the shot's first touch of the ground is inside the sector lines (on a line is out), at least 6 m from the
  inside of the rim, measured along the line through the circle's centre.
- Exit: after the landing, the robot's first touch of the rim's top or of the ground outside the circle is in the
  circle's rear half.
Then the robot stands for 1 s without a break (only the feet on the ground, the torso within 20 degrees of vertical,
the pelvis slower than 0.35 m/s). The success is called when the 1 s is complete.

Fouls (each fails the attempt): before the landing, any touch of the rim's top (its top inside edge included) or of
the ground outside the circle; touching the stop board anywhere but its inner side, or touching outside the circle in
its front half, before the exit; the shot below or behind the shoulder line, touched by anything other than the right
hand and the trunk, left resting on the trunk, or not pushed, before or at the release; the robot touching the shot
after the release, before it lands; a landing outside the sector or short of 6 m. Fall (a failure at any time): the
pelvis below 0.5 m, or any part other than the feet on the ground. Time limit: 60 s (6,000 control steps).

Graded: the live attempt, judged by the referee in the simulator service as it runs; nothing is replayed. The referee's
success call is an event: once it is made at some control step, the attempt is a success. It is never shown to the
agent and does not end the attempt: the physics goes on until the agent's `/finish`, the attempt's time limit, or the
end of the agent's time (2 h), and nothing after the call undoes it. A failure the referee calls before any
success (a foul, a fall, the physics diverging) ends the attempt at once with 0. Reaching the time limit or the end of
the session without a success call scores 0. The agent has 5 resets, each starting a new attempt from the
frozen start; only the last attempt (the one after the last reset) is graded, and a success in an earlier attempt does
not count. A simulator error raised by the agent's own call ends the attempt with 0. An attempt that does not start
from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
