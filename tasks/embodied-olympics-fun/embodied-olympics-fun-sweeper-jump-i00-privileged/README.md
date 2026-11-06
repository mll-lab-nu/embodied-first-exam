# embodied-olympics-fun-sweeper-jump-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-sweeper-jump-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sweeper_jump` / seed 0 |
| Oracle | `full` — Reference: walk, joint and lowcmd rows with the boom angle read privileged: it faces the boom, makes three tuck jumps with the soles 4-8 cm over the 0.30 m boom and stands 2 s, success at 21.1 s; 9 of 11 perturbed starts and 15 of 20 with its own gains +-3 % succeed, below the 9 of 10 bar (landings on the 0.9 m podium). Measured: success after 21.1 s of the 30 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Jump the sweeper: standing on your podium, jump over the padded boom each time it sweeps round, 3 times in a row without being hit, then stand still on the podium. (Embodied Olympics `sweeper-jump`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Neither built-in gait can jump: the robot must jump with its feet above a boom almost as high as its knees, at the moment a fast boom arrives, and land on a small podium in balance, three times. Each landing has to be absorbed and the robot re-centred on the podium before the boom comes round again.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: walk, joint and lowcmd rows with the boom angle read privileged: it faces the boom, makes three tuck jumps with the soles 4-8 cm over the 0.30 m boom and stands 2 s, success at 21.1 s; 9 of 11 perturbed starts and 15 of 20 with its own gains +-3 % succeed, below the 9 of 10 bar (landings on the 0.9 m podium). Measured: success after 21.1 s of the 30 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: You stand on a round podium, 0.9 m across and 0.4 m high, whose centre is 3.2 m from the axis of the motion base, facing the base. A foam boom 0.2 m thick, its axis 0.2 m above the podium's top, turns round the base counter-clockwise (seen from above) at 8.0 revolutions per minute, driven by a motor of at most 450.0 N m; it reaches 4.0 m from the axis, over the whole podium, and comes round once every 7.5 s. It is already turning at the start. A jump counts when the boom passes under both your feet while nothing of you touches anything (at the moment it passes each foot). You succeed when, after 3 counted jumps, your first contact is your feet on the podium and you then stand still for 1.0 s (only your feet on the podium, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s), before the boom comes round again. You fail at once if the boom touches any part of you (a hit; grabbing or holding it is a hit too), if any part of you touches the bed (the floor round the podium) or the motion base, if the boom passes through a foot that is not above it, on a fall (your pelvis less than 0.35 m above the podium's top, or any part of you other than your feet on the podium), on a landing after the last jump that is not on the feet, or after 30 s.

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
| Category | parkour-apparatus-balance |
| Rule book | No official rule book exists: the sweeper is a party and amusement game, not a sport. The closest real device is Galaxy Multi Rides' 'Meltdown' (US Meltdown operator manual: an eight-player game, each player standing on a podium round a motion base whose foam booms spin round, 'the aim of the game is to either duck under, or jump over the boom as it spins around'; players must not grab, hold or ride the booms; a player who is hit is out; one 1 hp spin motor on a speed dial, at most 15.82 rpm; foam boom attachments 220 lb for the two booms; riders at least 48 in (1.22 m) tall and at most 200 lb), the same game as the 'Sweeper' of the TV show Wipeout. Its rules as played: stay on your podium, jump the low boom each time it comes round, the last player not hit wins; deviations: the booms: Meltdown's dual attachment has two foam booms; here there is only the low boom you jump (the duck boom is left off: this family tests the jump), so the rotor is that one boom, 50.0 kg, half of the attachment's 220 lb · the dimensions: the manual gives none of the boom's height, length or thickness, nor of the podiums. The boom's axis is 0.2 m above the podium's top, the mid-shin of a rider of the minimum height (1.22 m), its foam 0.2 m thick, reaching 4.0 m from the axis over the podiums of a 30 ft bed, whose centres are 3.2 m from the axis; each podium a 0.9 m disc 0.4 m high (reasonable sizes, not published ones) · the podium and the bed: the inflatable podium is a rigid platform and the inflatable bed a firm floor (neither's give is modelled; touching the bed is out anyway) · the speed: the operator's dial is set to a steady 8.0 rpm (about half the machine's top speed), already turning at the start; the machine's program, which changes speed, is not used · the count: one player, and a run of 3 jumps in a row with no hit is the success (a round number: the game has no count, its last player standing wins); after the last jump the robot must stand still for 1.0 s on its podium before the boom comes round again · a hit is any touch of the boom on the robot (in the game a light touch may leave a player standing); a jump is a pass of the boom under both feet while nothing of the robot touches anything · the motor: the 1 hp drive is a speed loop with a torque limit of 450.0 N m at the boom (1 hp at the top speed of 15.82 rpm, through the gearbox), no gearbox backlash or compliance; the foam's contact is a critically damped spring of 0.02 s time constant (an estimate for a soft polyurethane pad) |
| Stages | jump 1 → jump 2 → jump 3 → landing → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `7f13421afecd1afc7cf8e52fa42d011c778e4508c399ced294a7c3355b434246` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
