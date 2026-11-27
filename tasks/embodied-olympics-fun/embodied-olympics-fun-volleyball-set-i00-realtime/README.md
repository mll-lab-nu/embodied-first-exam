# Embodied Olympics · volleyball set (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-set-i00-realtime` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | realtime, slowdown 1 |
| Instance | `volleyball_set`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Set the ball: with one overhead touch of your hands, send it high above the net and into the hitter's target along the
net.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high). The robot is the
setter, standing in its front zone facing along the net: the net 1.0 m to its right, the attack line 3.0 m from the
centre line to its left, the side line of position 2 3.0 m behind it. A volleyball (0.21 m across, 0.27 kg) is
tossed to it by a ball machine in the back court 3.0 s after the start and comes down above it. The referee's
stages, in order: set, above the net, in the target.
- Set: the ball's first contact after the toss, before it touches the floor, with the hands only (the parts beyond
  the wrists; one or both), after the ball has passed its highest point and with its centre above the top of the
  head (0.76 m above the waist joint along the trunk). Its contacts last at most 0.1 s; it is over when the ball has
  been clear of the robot for 0.03 s. The ball leaves the hands moving upward and at least 1.0 times as fast as just
  before they touched it.
- Above the net: the ball's centre then rises at least 1.0 m above the net's top.
- In the target: the ball's first contact with the floor is inside a circle of 1.0 m radius centred 1.0 m from the
  net on the robot's side and 1.0 m inside the side line ahead of the robot (the point under the ball's centre
  decides). The success is called at that contact.

Fouls (each fails the attempt at once):
- the robot touches the ball machine or the ball waiting in it;
- the ball touches the floor before or during the set;
- any part of the robot other than a hand touches the ball;
- the first contact comes before the ball has passed its highest point, or with the ball's centre not above the top of
  the head;
- the contacts last longer than 0.1 s (the ball held); the ball leaves the hands downward or slower than it came;
- a hand touches the ball again after the set;
- the ball does not rise 1.0 m above the net's top, or comes down outside the target;
- before the set the pelvis is farther from the net than the attack line (out of the front zone);
- the robot touches the net, an antenna or a post; a foot is on the floor wholly beyond the centre line.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit:
10 s (1,000 control steps).

Graded: the live attempt, judged by the referee in the simulator service as it runs; nothing is replayed. The clock
does not stop: an attempt starts paused at the frozen start, and from the agent's first `submit` one control step runs
every 10 ms × S of wall time (slowdown S = 1) whether or not the agent sends anything; when the planned
commands run out the last ones are held. The referee's success call is an event: once it is made at some control step,
the attempt is a success. It is never shown to the agent and does not end the attempt: the physics goes on until the
agent's `/finish`, the attempt's time limit, or the end of the agent's time (2 h), and nothing after the call
undoes it. A failure the referee calls before any success (a foul, a fall, the physics diverging) ends the attempt at
once with 0. Reaching the time limit or the end of the session without a success call scores 0. The agent has
5 resets, each starting a new, paused attempt from the frozen start; only the last attempt (the one after the
last reset) is graded. After the agent's first command, a simulator error or a simulator crash inside a control step
is the agent's 0; anything before the first command, a killed service, a failed resume or a reset that does not
rebuild the scene is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
