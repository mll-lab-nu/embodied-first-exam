# Embodied Olympics · penalty kick (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-penalty-kick-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Opponent | Goalkeeper dummy on a rail (scripted): after the kick it moves along the goal line to block the ball |
| Instance | `penalty_kick`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Take a penalty kick: with one kick, send the ball past the goalkeeper dummy into the goal.

## Success criteria
A size-5 football lies on the penalty mark, 3.0 m ahead of the robot; the goal (7.32 m wide, 2.44 m high) is 11 m
beyond it. A goalkeeper dummy (a board 1.9 m high, 0.6 m wide, 80 kg) stands on the goal line at the centre of the goal
on a carriage that runs on a rail. From 0.25 s after the kick its motor (at most 800 N) drives it at up to 3.0 m/s
towards the point where the ball, going on as it moves at that moment, would cross the line; it blocks the ball, and a
hit pushes it along the rail. The referee's stages, in order: kick, goal.
- Kick: the first contact of a foot or an ankle (the parts below the shin) with the ball. Every such contact within
  0.15 s of the first belongs to the one kick.
- Goal: the whole ball is over the goal line between the posts and under the bar. It may touch the posts, the bar,
  the dummy and the ground on the way. The success is called at that moment.

Fouls (each fails the attempt): any other part of the robot touches the ball at any time; a foot touches the ball
again more than 0.15 s after the first contact; the ball is not moving towards the goal line at the end of the kick;
the whole ball crosses the goal line outside the goal; after the kick, the ball is slower than 0.1 m/s for 1.0 s
without a goal. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet on the ground.
Time limit: 15 s (1,500 control steps).

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
