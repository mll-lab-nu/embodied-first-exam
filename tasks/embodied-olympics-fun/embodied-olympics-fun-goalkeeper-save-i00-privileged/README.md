# embodied-olympics-fun-goalkeeper-save-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-goalkeeper-save-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `goalkeeper_save` / seed 0 |
| Oracle | `full` — Reference: the H1-2 walks along the goal line into each shot's line (walking policy, closed loop on the pelvis), feet on the line at each kick; three 20 m/s machine shots hit the body and stay out. It learns each machine's real crossing (scatter up to 0.4 m) and side offsets over privileged resets (2-6 attempts); 10 of 10 perturbations (aims, speeds 19 and 21 m/s, kick time) succeed. Measured: success after 26.7 s of the 27 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Keep goal: three penalty kicks are shot at the official goal you stand in; keep every ball out, with a foot on the goal line at each kick. (Embodied Olympics `goalkeeper-save`: one Unitree H1-2 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Each ball arrives about 0.55 s after it leaves the machine at 20 m/s and 0.43 kg: the body has to be in its line when it is kicked, standing with a foot on the line, and the ball must come off it away from the goal; between the kicks a 67 kg robot whose walking policy makes about 0.3 m/s sideways has to cross up to 2.5 m of goal and stop on the line again in time.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: the H1-2 walks along the goal line into each shot's line (walking policy, closed loop on the pelvis), feet on the line at each kick; three 20 m/s machine shots hit the body and stay out. It learns each machine's real crossing (scatter up to 0.4 m) and side offsets over privileged resets (2-6 attempts); 10 of 10 perturbations (aims, speeds 19 and 21 m/s, kick time) succeed. Measured: success after 26.7 s of the 27 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You are the goalkeeper. You stand on the goal line, in the middle of the goal, facing the penalty mark 11.0 m in front of you (+x). The goal behind you is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick, on the goal line, the net 2.0 m deep). Three ball machines stand on the line through the penalty mark, 0.6 m apart (the middle one over the mark), their exits 0.6 m above the ground; each holds one size-5 football (0.22 m across, 0.43 kg, in air) and shoots it once, at 20.0 m/s with no spin: the first (on your right as you face them, at y = -0.6 m) is fed at 6.0 s and aimed at the point of the goal's plane -0.8 m to your left (negative: to your right) and 0.9 m above the ground; the middle one 9.0 s later, aimed at 0.8 m and 1.1 m; the third (on your left) 9.0 s after that, aimed at -0.5 m and 0.95 m. A shot is kicked when its ball leaves the machine's wheels (about 0.1 s after it is fed). At that moment (Law 14) you must be on your feet (nothing but the feet on the ground), with at least part of one foot touching or above the goal line between the posts, and touching neither the posts, the crossbar nor the net; otherwise you fail. After the kick you may move as you like and use any part of you: hands, arms, body, legs, no grip is needed, and you may go to ground. A goal is the whole ball over the goal line between the posts and under the crossbar; you fail at the first goal, by any of the three balls at any time (also a ball that comes back off you or the posts). A shot is saved when 2.5 s have passed since its kick without a goal; you succeed when all three are saved. You also fail if your pelvis leaves the goal area (5.5 m in front of the goal line, 9.16 m to each side of the goal's centre), if you touch a machine or a ball that has not yet been kicked, or after 27 s.

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
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide on the goal line, the penalty mark 11 m from the goal line, the goal area 5.5 m x 18.32 m), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the crossbar), Law 12 (a goalkeeper may handle the ball in their own penalty area) and Law 14 (the penalty kick: the goalkeeper remains on the goal line, facing the kicker, between the goalposts, without touching the goalposts, crossbar or goal net, until the ball has been kicked; when the ball is kicked the goalkeeper must have at least part of one foot touching, or in line with, the goal line); deviations: Law 14 (the kicker): each penalty is shot by a two-wheel ball machine instead of a kicker: three machines, one ball each (a machine holds one ball per load), their exits 0.6 m above the ground on the penalty mark's line, 0.6 m apart across it (the middle one over the mark; the Law puts the ball on the mark). Each is aimed before the attempt at a point of the goal's plane that the rules state, and throws at 20.0 m/s, no spin: a real keeper reads a kicker; here the aim is stated instead. The elevation is computed for the ball's drag in air and trimmed by 0.45 degrees (measured in this venue: untrimmed, the shots crossed the line about 0.1 m low); a machine's own scatter (about 2 percent in speed and 2 degrees in direction, its maker's measurement) stays. · Law 10 (kicks from the penalty mark): three penalties against the same goalkeeper, 9.0 s apart, in one attempt; every one must be saved. · Law 14 (the goalkeeper between kicks): between the penalties the goalkeeper stays inside the goal area (only the moment of each kick is regulated by the Law). · Law 1: only the goal end of the field is there (the penalty area, the goal area and the mark are painted); the goal's net is a rigid cage 2.0 m deep. |
| Stages | save 1 → save 2 → save 3 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `36ddfcffb146e3f7815e5c531250d400cb31f0ed875037b82ac05d4aa5407ca2` |
| Episode | 2700 control steps (27 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
