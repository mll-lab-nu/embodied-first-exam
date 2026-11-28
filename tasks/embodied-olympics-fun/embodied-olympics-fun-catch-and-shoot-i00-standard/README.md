# Embodied Olympics · catch and shoot (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-catch-and-shoot-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `catch_and_shoot`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Catch the pass with both hands, then shoot it into the basket from where you stand, without travelling.

## Success criteria
The official basket (ring top 3.05 m above the floor); about 2.0 s after the start a passing machine 4.0 m away sends
the robot a chest pass of about 9 m/s. A hand is on the ball while it touches it (gaps shorter than 0.03 s included).
The referee's stages, in order: catch, release, through the ring.
- Catch: before the ball touches the floor, both hands are on it together for 0.1 s without a break. Earlier touches
  of one hand or both are allowed.
- Release: from the catch the ball stays in the hands until no hand is on it (a slip or drop is a release too). From
  the catch to the release no travelling: with both feet on the floor at the catch, the first foot lifted makes the
  other the pivot foot, the pivot foot (before any lift, either foot) may not slide more than 0.2 m, and once it has
  left the floor no foot may touch the floor again before the release; with a foot off the floor at the catch, at most
  2 steps (never the same foot twice in a row), and no foot down again after them before the release.
- Through the ring: the ball's centre goes down through the ring's plane inside the ring and on down to one ball
  diameter below it. The success is called then.

Fouls (each fails the attempt at once): the robot touches the ball before the pass; from the pass to the release, the
ball touches a part other than the hands; the ball touches the floor before the catch, or at any time before it is
through the ring; travelling; the robot touches the ball more than 0.05 s after the release; the ball's centre comes
up through the ring from below. Fall (a failure at any time): the pelvis below 0.35 m, or any part other than the feet
on the floor. Time limit: 15 s (1,500 control steps).

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
