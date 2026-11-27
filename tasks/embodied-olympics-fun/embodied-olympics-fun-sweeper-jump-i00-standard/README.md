# Embodied Olympics · sweeper jump (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-sweeper-jump-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `sweeper_jump`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Jump the sweeping boom 3 times in a row without being hit, then land on your podium and stand still before it comes
round again.

## Success criteria
The robot stands on a round podium 0.90 m across and 0.40 m high. A 50 kg foam boom 0.20 m thick, its axis 0.20 m
above the podium's top, turns counter-clockwise (seen from above) round a motion base at 8 rpm, once every 7.5 s,
driven by a motor of at most 450 N m; it reaches over the whole podium and is already turning at the start. The
referee's stages, in order: jump 1, jump 2, jump 3, landing, stand.
- A jump counts when the boom passes under both feet, and at the moment it passes each foot the sole of that foot is
  above the boom's top (0.30 m above the podium's top) and nothing of the robot touches anything. A foot the boom
  passes that is not above it, or a pass while the robot touches something, fails the attempt; so does the boom
  passing one foot and not the other within half a turn.
- Landing: after the third jump, the robot's first contact is made by the feet only; otherwise the attempt fails.
- Stand: the robot then stands for 1 s without a break with only its feet on the podium, the torso within about 20
  degrees of vertical, the pelvis slower than 0.35 m/s. The success is called when the 1 s is complete.

Fouls (each fails the attempt at once): the boom touches any part of the robot (a hit; grabbing it counts); any part
of the robot touches the bed round the podium, the motion base or another podium. Fall (a failure at any time): the
pelvis lower than 0.35 m above the podium's top, or any part other than the feet on the ground. Time limit: 30 s
(3,000 control steps).

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
