# Embodied Olympics · volleyball bump (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-bump-i00-privileged` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | privileged |
| Instance | `volleyball_bump`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Pass the serve: with one forearm pass, send the ball up above net height and down onto the setter's target.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high). The robot stands in
its own half, facing the net, 6.0 m from it, midway between the side lines. A volleyball (0.21 m across, 0.27 kg) is
served over the net by a ball machine behind the far end line 3.0 s after the start: a float serve that comes down in
the robot's part of the court. The referee's stages, in order: pass, above the net height, in the target.
- Pass: the ball's first contact after the serve, on the robot's side of the net and before it touches the floor,
  with the forearms or hands only (the arm from the elbow down; one arm or both). Its contacts last at most 0.1 s; it
  is over when the ball has been clear of the robot for 0.03 s.
- Above the net height: after the pass, the ball's centre rises above 2.43 m.
- In the target: the ball's first contact with the floor is inside a circle of 1.0 m radius centred 1.0 m from the
  net on the robot's side and 1.5 m to the right of the court's middle (the point under the ball's centre decides).
  The success is called at that contact.

Fouls (each fails the attempt at once):
- the robot touches the ball machine or the ball waiting in it;
- the robot touches the ball before it has crossed the net;
- the ball touches the floor before or during the pass;
- any part of the robot other than a forearm or a hand touches the ball;
- the pass's contacts last longer than 0.1 s (the ball held); a forearm or hand touches the ball again after the
  pass;
- the ball comes down outside the target, or without having risen above the net's height;
- the robot touches the net, an antenna or a post; a foot is on the floor wholly beyond the centre line.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit:
10 s (1,000 control steps).

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
