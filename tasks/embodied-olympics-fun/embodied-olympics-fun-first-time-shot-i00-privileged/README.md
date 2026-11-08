# embodied-olympics-fun-first-time-shot-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-first-time-shot-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `first_time_shot` / seed 0 |
| Oracle | `full` — Reference: a scripted standing side-foot kick of the G1 (joint targets, centre-of-mass feedback ankle balance on the left foot, the right hip turned out, the swing start timed within a control step on the rolling ball), then the walking policy recovers: the ball is met at 3.1 m/s and shot at 5.0 m/s, a goal at 9.16 s; 9 of 10 perturbations (gains, release time, ramp height) succeed. Measured: success after 9.22 s of the 15 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Shoot first time: the football rolls down a ramp and across in front of you; with one touch of a foot send it into the official goal 11 m away. (Embodied Olympics `first-time-shot`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The ball crosses the width of a foot in a few hundredths of a second and at right angles to the goal: the foot has to arrive with a swing or a run of its own at that moment, angled so that the pass's sideways speed is turned towards the goal, faster than the ball came, by a 33 kg robot that has no kicking skill and has to stay on its feet.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: a scripted standing side-foot kick of the G1 (joint targets, centre-of-mass feedback ankle balance on the left foot, the right hip turned out, the swing start timed within a control step on the rolling ball), then the walking policy recovers: the ball is met at 3.1 m/s and shot at 5.0 m/s, a goal at 9.16 s; 9 of 10 perturbations (gains, release time, ramp height) succeed. Measured: success after 9.22 s of the 15 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You stand facing the goal (+x), 0.3 m behind the pass line: the line through the penalty mark parallel to the goal line, which is 11.0 m beyond it. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line you face along; there is no goalkeeper. A size-5 football (0.22 m across, 0.43 kg, in air) rests against a gate on a wooden ball ramp: the ramp's foot is on the pass line 4.0 m to your left, it rises away from you at 20.0 degrees (curving into the grass at its foot) and the ball waits 1.2 m up it. At 2.0 s a servo swings the gate open; the ball rolls down the ramp and along the pass line from your left to your right. The shot is the ball's first contact with you after the release: with a foot or an ankle of yours (the parts below the shin), while the ball's centre is between the lines of the two posts (7.32 m wide, measured across the pass). Every contact within 0.15 s of the first belongs to the one touch, which is over when the ball has been clear of you for 0.03 s; it must be a shot: the ball's speed when it leaves your foot is at least 1.0 times its speed just before the foot touched it, and it is moving towards the goal line. You succeed at the moment the whole ball is then over the goal line between the posts and under the bar; after the shot it may touch the ground, the posts and the bar. You fail if any part of you other than a foot or an ankle touches the ball at any time, if the first touch is outside the lines of the posts, if the touch lasts longer than 0.15 s, if the ball leaves the foot slower than that or not towards the goal line, if you touch the ball again after the shot, if the pass rolls past the line of the far post untouched, if the whole ball crosses the goal line outside the goal, if after the shot the ball has been slower than 0.1 m/s for 1.0 s, if you touch the ramp or its gate, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 15 s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the penalty mark 11 m from the goal line, the penalty area, the goal area), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the bar), Law 12 (handball) and the glossary (a kick is a contact with the foot or the ankle). The drill itself, a square pass struck first time (one touch) at goal from the penalty mark, is a coaching exercise, not a rule-book event: the pass and the one-touch standard are the benchmark's; deviations: The pass comes from a ball ramp instead of a team-mate: the ball rests against a gate 1.2 m up a 20.0 degree wooden ramp whose foot is 4.0 m to your left on the pass line; at 2.0 s a servo (stall torque 4.1 N m) swings the gate open and gravity rolls the ball down and across, along the line through the penalty mark parallel to the goal line. The same pass in every attempt; the pitch is level and uniform (the official ball's rolling resistance, no bobble), no wind. · Law 3: no goalkeeper and no defender: a finishing drill on an open goal, not a match situation. · The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one touch, with a foot or an ankle only, while the ball is between the lines of the two posts (the shot is taken from in front of the goal). · A shot is judged by numbers instead of a referee's eye: every contact within 0.15 s of the first is the one touch, and a shot is a ball that leaves the foot at least 1.0 times as fast as it arrived (a ball that only rebounds from a foot held in its path leaves slower: it is not a shot). · Law 1: only the goal end of the field is there (the penalty area, the goal area and the mark are painted); the goal's net is a rigid cage 2.0 m deep. |
| Stages | shot → goal |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c7c02e1e6482888bca9be375f4e8aab052fbdf41c501e426cf393ff5fec878bf` |
| Episode | 1500 control steps (15 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
