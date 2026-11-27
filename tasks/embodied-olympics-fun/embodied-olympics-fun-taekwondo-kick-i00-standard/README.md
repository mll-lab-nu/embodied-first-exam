# Embodied Olympics · taekwondo kick (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-taekwondo-kick-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `taekwondo_kick`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Kick the dummy's trunk protector once, hard, with a foot, then stand clear of it.

## Success criteria
A free-standing body-opponent dummy (one rigid body 1.52 m tall: a 122 kg round base 0.61 m across, a stem, an 8 kg
torso and a head). Its torso wears a taekwondo trunk protector, 0.32 m wide, from 0.78 m to 1.12 m above the floor,
facing the robot; its front is 0.58 m in front of the robot's pelvis at the start. The referee's stages, in order: kick,
stand.
- Kick: the robot's first touch of the dummy is made with a foot (the part below the ankle; the lower leg counts only
  where its contact lies below the ankle joint and from 0.08 m behind to 0.15 m in front of it) and lands on the
  protector only. It is an impact: the touch lasts at most 0.05 s (it ends when foot and dummy have been apart for 0.03
  s), and the protector receives an impulse of at least 7.2 N s (the contact forces summed over the touch). The stage is
  called when the touch ends.
- Stand: after the kick, the robot stands for 2 s without a break: both feet and nothing else on the floor, no part
  touching the dummy, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. The success is
  called at the end of the 2 s.

Fouls (each fails the attempt at once):
- any part of the robot other than a foot (as defined above) touches the dummy;
- the kick touches the dummy anywhere but the protector;
- the kick's contact lasts longer than 0.05 s (a push);
- the kick's impulse is below 7.2 N s;
- after the kick, any part other than a foot touches the dummy (a foot may touch it again; it scores nothing more).
Fall (a failure at any time): the pelvis lower than 0.35 m, or any part other than the feet on the floor. Time limit: 15
s (1,500 control steps).

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
