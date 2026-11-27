# Embodied Olympics · badminton serve (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-badminton-serve-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Instance | `badminton_serve`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Serve the shuttle: from your right service court, let it go from your left hand and hit it, cork first and below 1.15 m,
with the racket in your right hand over the net into the service court diagonally opposite.

## Success criteria
A BWF court, singles. The shuttle starts held by its feathers in the left hand; the racket is held in the right hand
by contact and friction. The robot serves from its right service court into the receiver's right service court,
diagonally opposite. The referee's stages, in order: release, hit, over the net, in.
- Racket, at all times: it stays in the right hand (a break of more than 0.05 s is a fault) and never touches the
  floor, the net or a post.
- Release: the left hand lets the shuttle go; it is let go once it has touched nothing of the robot for 0.03 s. Before
  that the racket may not touch it; after it nothing of the robot but the racket may touch it.
- Hit: the racket hits the shuttle before it reaches the floor, the net or the net's plane. At the first instant of
  contact the cork base touches the racket, the whole shuttle is lower than 1.15 m, the shuttle moves at most 4.0 m/s,
  and the racket head is in a forward movement (its speed towards the net rose above 0.5 m/s and has not fallen below
  0.1 m/s). The service starts at the earlier of the release and the start of that movement; a forward movement that
  starts after the release and stops before the hit is a fault. From the start of the service to the hit, both feet
  stand inside the server's service court, touching neither its lines nor anything outside it, each foot on the floor
  all the time (gaps of at most 0.02 s) and moving at most 0.03 m. The hit is one contact (contacts less than 0.03 s
  apart are one), lasts at most 0.02 s, and when it is over the shuttle is faster than when it reached the racket and
  rising.
- Over the net: the shuttle passes the net's plane above the net's top edge, between the posts (it may touch the net).
- In: its first contact with the floor is inside the receiver's right service court, lines included. The success is
  called then.

Fouls (each fails the attempt at once): any rule above broken; a second hit; the shuttle touching the robot after the
hit, touching a post, passing through or under the net or outside the posts, or landing on the robot's side or
outside that service court; any part of the robot touching the net or a post. Fall (a failure at any time): the pelvis
below 0.35 m, or any part other than the feet on the floor. Time limit: 15 s (1,500 control steps).

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory()` writes it: an `actions` array of sim rows, one per
10 ms control step, and the task's family name. After the agent's session it is replayed once, open-loop, from the
frozen start, in a fresh process of a separate verifier container without network. Rows run one per control step
until the referee calls the attempt; rows after the call, and rows past the attempt's time limit, are not run. The
task is passed if the referee has called a success when the replay stops. If the rows run out before the referee's
call, the task is not passed. A row the robot cannot run (its first value, the mode, is not one of the robot's modes)
ends the replay at that row without a pass.

The physics diverging (a non-finite state, a bad acceleration, or the robot or a prop faster than 150 m/s) ends the
attempt as a failure, unless a success was called in an earlier control step. Only the trajectory is scored (`gen.py`
and `NOTES.md` are not). A missing file, a file that is not such an array (a link, over 64 MB, more than 40,000 rows,
the wrong row width), a file for another task, or a non-finite value in the rows that are used scores 0. An image that
no longer rebuilds the frozen start, or a replay that crashes or runs over 600 s, is an infrastructure failure, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
