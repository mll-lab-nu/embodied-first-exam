# Embodied Olympics · header (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-header-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `header`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Head the cross from the wing into the goal, past the goalkeeper dummy.

## Success criteria
The robot stands on the edge of the goal area, 5.5 m from the goal line. The goal is 7.32 m wide between the posts
and 2.44 m high under the bar; a goalkeeper dummy (a board 1.9 m high and 0.6 m wide) is held on the goal line at the
goal's centre. A ball machine on the left wing, 20 m away, crosses a lofted ball at about 2.9 s that passes in front
of the robot at head height. The referee's stages, in order: header, goal.
- Header: the ball's first contact after the cross is with the head (the part of the trunk-and-head shell at least
  0.53 m above the waist joint along the trunk), before the ball has touched the ground. Every contact until the ball
  has been clear of the robot for 0.03 s is the same header; it lasts at most 0.15 s, and the ball leaves at least as
  fast as it came.
- Goal: the whole ball then crosses the goal line between the posts and under the bar. After the header it may touch
  the ground, the posts, the bar and the dummy.

Fouls (each fails the attempt): before the cross leaves the machine, the robot touches the machine or the ball, or
its pelvis comes within 9.15 m of the machine; the ball touches the ground before the header; the ball touches the
shell below the head, or any other part of the robot; the header lasts longer than 0.15 s, or the ball leaves it
slower than it came; the robot touches the ball again after the header; the whole ball crosses the goal line before
the header, or outside the goal; after the header the ball is slower than 0.1 m/s for 1 s. Fall rule: on, the pelvis
below 0.35 m or any part other than the feet on the ground. Time limit: 10 s (1,000 control steps).

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
