# Embodied Olympics · wall ball (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-wall-ball-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `wall_ball`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
From behind the line, throw the ball at the target circle on the wall, then catch the rebound in a hand before it lands
and hold it.

## Success criteria
A wall stands 5.0 m beyond the line the robot stays behind; the target is a circle 0.5 m across painted on it, its
centre 1.5 m above the ground, straight ahead of the robot. A tennis ball (0.067 m across, 0.0577 kg) starts in the
right hand; both hands are five-finger hands that hold things by contact and friction only. A hand holds the ball
while the ball touches its fingers and its thumb or palm, with the ball's centre on the palm's side of the hand and
within 0.12 m of the hand's grasp point. The referee's stages, in order: release, target, catch, hold.
- Release: the ball has touched no part of the robot for 0.05 s (it is released at its last touch; once).
- Target: the first thing it touches after that is the wall, at a point inside the target circle.
- Catch: a hand then holds the ball (either hand), before the ball has touched the ground; before the catch the
  rebound may touch only the hands and forearms.
- Hold: the ball has been held for 1.0 s from the catch, never unheld for more than 0.05 s. The success is called at
  the end of the 1.0 s.

Fouls (each fails the attempt at once):
- any part of the robot touches the ground on or beyond the line, at any time;
- the ball touches the ground, at any time;
- the ball hits the wall outside the circle;
- after the release and before the wall, any part of the robot touches the ball or a hand holds it (the right arm
  may still brush it during the first 0.15 s after the release);
- before the catch the rebound touches a part other than a hand or a forearm;
- after the catch the ball is unheld for more than 0.05 s.
Fall (a failure at any time): the pelvis lower than 0.5 m, or any part other than the feet on the ground. Time limit:
15 s (1,500 control steps).

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
