# Embodied Olympics · table tennis return (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-table-tennis-return-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | privileged |
| Opponent | A ball machine on the far side of the table (scripted), serving one fixed legal service at about 3 s |
| Instance | `table_tennis_return`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Return the serve: after it bounces once on your side, hit it with the paddle in your right hand onto the opponent's
side, without letting go of the paddle.

## Success criteria
An official table (2.74 m by 1.525 m, its playing surface 0.76 m above the floor, a net 0.1525 m high). The robot
holds a free racket (0.14 kg, a 0.15 m square blade on a 0.1 m handle) in its right hand by contact and friction
only. About 3.0 s after the start a ball machine on the far side serves one fixed legal service: the ball bounces on
the server's court, passes the net and bounces on the robot's court. The referee's stages, in order: bounce, strike,
opponent's court.
- Bounce: the ball bounces once on the robot's court (ball contacts with the table less than 0.02 s apart are one
  bounce).
- Strike: the ball is then struck with the racket's blade or the right hand; all such contacts within 0.05 s of the
  first are one strike.
- Opponent's court: after the strike, the ball's next table contact is on the opponent's half of the playing surface
  (directly or after touching the net; over or around the net). The success is called at that touch.

Fouls (each fails the attempt at once):
- the racket has not been held by the right hand's fingers and its thumb or palm for more than 0.05 s (dropped,
  thrown or slipped out); the racket touches any part of the robot other than the right hand, or the floor;
- the robot or the racket touches the ball before the service has left the machine, or before its bounce on the
  robot's court; the ball bounces a second time on the robot's court before the strike;
- anything other than the blade or the right hand touches the ball (the racket's handle included); the blade or the
  right hand touches the ball again more than 0.05 s after the first contact;
- after the strike the ball touches the robot's own court, the side of the table (the ball's centre below the playing
  surface) or the floor before the opponent's court; the ball touches the floor at any time;
- any part of the robot or the racket touches the net; the left hand touches the playing surface once the ball is in
  play;
- a service that touches the net or does not bounce first on the server's court and then on the robot's.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Anything
else of the robot, the racket included, may touch the table. Time limit: 8 s (800 control steps).

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
