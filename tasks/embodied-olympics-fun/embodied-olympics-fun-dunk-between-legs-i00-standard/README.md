# Embodied Olympics · dunk between the legs (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-dunk-between-legs-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `dunk_between_legs`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Dribble from the top of the key, bounce the ball once between your legs, gather it in both hands and, with at most two
steps, dunk it. Then let go, land on your feet and stand.

## Success criteria
A FIBA court with the official basket (ring top 2.39 m above the floor); the robot starts standing, the ball held
between its hands. A hand is on the ball while it touches it (gaps shorter than 0.03 s included). The referee's
stages, in order: dribble, between the legs, gather, dunk, stand.
- Start: the first foot lifted makes the other the pivot foot; the pivot foot (before any lift, either foot) may not
  slide more than 0.2 m, nor leave the floor before the ball has left the hands; the ball may not touch the floor
  while in the hands.
- Dribble: the ball, out of the hands, touches the floor with no hand on it. During the dribble the robot plays it with
  one hand at a time; between two hand touches (the release counts as one) the ball must touch the floor; one hand's
  touch lasts at most 0.3 s; the ball touches no part but the hands, and its centre stays within 2.0 m horizontally of
  the pelvis.
- Between the legs: at a hand touch, the ball's last passage through the plane of the leg gate since the previous touch
  was inside the gate (the triangle of the two soles and the crotch, up to the lower knee joint, with an area of at
  least 0.02 m2), with no hand on the ball and the ball moving through the plane at 1.0 m/s or more, and the ball is now
  on the other side of the plane from the previous touch.
- Gather: both hands on the ball at the same moment ends the dribble; before a bounce between the legs this fails the
  attempt. After the gather the ball stays in the hands until its centre has entered the ring, and may not touch the
  floor. At most 2 steps (a foot touching down after at least 0.03 s off the floor; both feet within 0.03 s are one
  step; never the same foot twice in a row), and a foot on the floor may not slide more than 0.2 m.
- Dunk: the ball's centre goes down through the ring's plane inside the ring while both hands are on it, or a hand
  whose latest contact is at least 0.06 m above the ball's centre, and on down to one ball diameter below the ring.
- Stand: after the dunk, no hand on the ball and, for 1.0 s without a break, only the feet on the ground, the torso
  upright (tilt cosine at least 0.94), the pelvis slower than 0.35 m/s. The success is called when the 1.0 s are
  complete.

Fouls (each fails the attempt at once): any rule above broken; the ball through the ring before the gather; the ball
coming up through the ring from below; the ball or any part of the robot touching the floor on or outside the end line
or a side line; the robot touching the basket (ring, plate or backboard) for more than 0.3 s in all. Fall (a failure
at any time): the pelvis below 0.35 m, or any part other than the feet on the floor. Time limit: 40 s (4,000 control
steps).

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
