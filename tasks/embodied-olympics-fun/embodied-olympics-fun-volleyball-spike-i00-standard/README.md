# Embodied Olympics · volleyball spike (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-spike-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `volleyball_spike`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Spike the set: jump and hit the ball with a hand above the net down into the opponent's court, then land on your feet
without touching the net and stand.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high, an antenna above each
side line). The robot is the outside hitter, standing on its attack line facing the net 3.0 m ahead, the left side line
1.0 m to its left. A volleyball (0.21 m across, 0.27 kg) is set by a ball machine from the robot's right 3.0 s after the
start; it rises to about 4.5 m and comes down 0.5 m from the net in front of the robot. The referee's stages, in order:
spike, over the net, in the court, landing.
- Spike: the ball's first contact after the set, before it touches the floor, is with a hand (the parts beyond the
  wrist; one or both), after the ball has passed its highest point, at contact points all higher than the net's top,
  while the robot is in the air (nothing of it touching the floor or anything else). Its contacts last at most 0.1 s
  (over when the ball has been clear of the robot for 0.03 s); the ball leaves the hand moving downward and at least 1.0
  times as fast as just before the hand touched it.
- Over the net: the ball's centre crosses the net's plane above the net's top and between the side lines (it may touch
  the net).
- In the court: the ball's first contact with the floor is in the opponent's court (9.0 m by 9.0 m, lines included).
  From then on the ball is dead and what it touches is not judged.
- Landing: the flight of the spike was a jump (when it lands, the pelvis had risen at least 0.1 m above its height when
  the feet left the floor), and the robot then stands for 1.0 s without a break: only the feet on the floor, the trunk
  within about 20 degrees of upright, the pelvis slower than 0.35 m/s. The success is called at the end of the 1.0 s.

Fouls (each fails the attempt at once):
- the robot touches the ball machine or the ball waiting in it;
- the ball touches the floor before the spike;
- any part of the robot other than a hand touches the ball;
- the first contact comes before the ball has passed its highest point, from the floor, with a contact point at or below
  the net's top, or in a flight in which the pelvis does not rise 0.1 m;
- the contacts last longer than 0.1 s; the ball leaves the hand upward or slower than it came;
- a hand touches the ball again;
- the ball touches an antenna, crosses the net's plane before the spike, under the net's top or outside the side lines,
  or lands anywhere but in the opponent's court;
- the robot touches the net, an antenna or a post at any time; a foot is on the floor wholly beyond the centre line.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit: 12
s (1,200 control steps).

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
