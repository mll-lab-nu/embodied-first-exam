# Embodied Olympics · volleyball serve (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-volleyball-serve-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `volleyball_serve`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Serve: toss the ball off your left palm and hit it with one hand over the net into the opponent's court, within 8 s.

## Success criteria
An official volleyball court (9.0 m by 9.0 m on each side of the net; the net's top 2.43 m high, with an antenna
above each side line). The robot stands behind the end line, facing the net, midway between the side lines; the end
line's outer edge is 0.5 m ahead of the pelvis. A volleyball (0.21 m across, 0.27 kg) starts resting on the robot's
open left palm; the hands have no fingers and no grip. The referee's stages, in order: toss, hit, over the net, in
the court.
- Toss: the ball has touched no part of the robot for 0.03 s; the release is the end of its last contact with a hand.
  For 0.1 s from the release the hand that held it may still touch it, and the ball must be clear of that hand when
  that time ends.
- Hit: the ball's next contact, with one hand or one arm (hand, forearm or upper arm of the same side), beginning
  within 8.0 s of the start. The ball has been clear of the robot for at least 0.1 s before it and moves at most
  5.0 m/s just before it; its contacts last at most 0.1 s (over when the ball has been clear for 0.03 s); the ball
  leaves faster than it arrived. At its first contact no foot touches the court (the end line included) or the floor
  beyond the side lines' extensions; in the air, this holds for where the robot took off.
- Over the net: the ball's centre crosses the net's plane above the net's top and between the side lines (it may
  touch the net).
- In the court: the ball's first contact with the floor is in the opponent's court (9.0 m by 9.0 m, lines included).
  The success is called at that contact.

Fouls (each fails the attempt at once):
- before the toss, the ball touches the floor or a part of the robot other than the hands (the palm pads and wrists);
- the hit has not begun 8.0 s after the start;
- after the toss the ball touches the floor before the hit, or stays on the hand (not tossed);
- the hit comes less than 0.1 s after the ball was last touched, the ball reaches it faster than 5.0 m/s, the hit
  touches more than one arm or another part, lasts longer than 0.1 s, or does not add speed;
- a foot fault at the hit (as above);
- the robot touches the ball again after the hit;
- the ball touches an antenna, crosses the net's plane before the hit, under the net's top or outside the side lines,
  or lands anywhere but in the opponent's court.
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit:
12 s (1,200 control steps).

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
