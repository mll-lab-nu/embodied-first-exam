# Embodied Olympics · skateboard ollie (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-skateboard-ollie-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `skateboard_ollie`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Do an ollie: pop the skateboard into the air with your feet, land on it with both feet and all four wheels down, and
stand still on it.

## Success criteria
A skateboard (0.8 m deck with a kicktail and a turned-up nose, four wheels on steering trucks) rests on a level
plaza; the robot stands across it, feet on the deck. Nothing holds the feet to it but grip tape. The referee's stages,
in order: pop, clear, landed, stand.
- Pop: the board leaves the ground (no part of it touching anything but the robot) with a foot on its deck as it
  leaves.
- Clear: in that same flight of the board, every part of it (deck, trucks, wheels) is at least 0.05 m above the
  ground. A pop that does not clear may be followed by another.
- Landed: then all four wheels are on the ground (each within 0.005 m of it) with both feet on the deck.
- Stand: for 1 s without a break, both feet on the deck (contact breaks of at most 0.05 s), all four wheels on the
  ground and the pelvis slower than 0.35 m/s. The success is called when the 1 s is complete.

Fouls (each fails the attempt): any part of the robot other than the feet and shins touches the board; the board
touches the ground with its deck tilted more than 60 degrees from level; after the landing, a foot off the deck for
more than 0.2 s, or the torso tilted more than about 37 degrees from upright (the cosine of its tilt below 0.8).
Fall (a bail, a failure at any time): any part of the robot, a foot included, touching the ground, or the pelvis
below 0.3 m. Time limit: 8 s (800 control steps).

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
