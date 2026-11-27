# Embodied Olympics · rugby conversion (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-rugby-conversion-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `rugby_conversion`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Kick the conversion: with one kick, send the ball from its tee over the crossbar between the posts.

## Success criteria
A rugby ball stands upright on a kicking tee in front of the robot's right foot. The goal line is 5 m beyond the ball;
the posts on it are 5.6 m apart (inner faces), centred on the ball, with the top of the crossbar 3 m above the ground.
The referee's stages, in order: kick, goal.
- Kick: the first contact of a foot with the ball (the foot below the ankle, or the lower leg where it lies over the
  foot: from 0.08 m behind to 0.15 m ahead of the ankle joint and at most 0.12 m above it). Every foot contact within
  0.15 s of the first belongs to the same kick.
- Goal: the ball's centre passes the goal line's vertical plane above the crossbar and between the posts (extended
  upwards), and goes on to 0.4 m beyond that plane. The ball may touch the bar or a post on the way. The success is
  called at that point.

Fouls (each fails the attempt): any part of the robot other than a foot touches the ball, at any time; a foot touches
the ball outside the kicking zone above; a touch of the ball more than 0.15 s after the kick; the ball touches the
ground (not the tee) after the kick before it has scored; the ball passes the goal line's plane under the crossbar or
outside the posts. Fall, judged only before the kick: the pelvis below 0.35 m, or any part other than the feet on the
ground. A fall after the kick does not end the attempt. Time limit: 60 s (6,000 control steps).

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
