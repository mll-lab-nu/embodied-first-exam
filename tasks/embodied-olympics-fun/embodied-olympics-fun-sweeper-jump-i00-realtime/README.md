# embodied-olympics-fun-sweeper-jump-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-sweeper-jump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sweeper_jump` / seed 0 |
| Oracle | `full` — Reference: walk, joint and lowcmd rows with the boom angle read privileged: it faces the boom, makes three tuck jumps with the soles 4-8 cm over the 0.30 m boom and stands 2 s, success at 21.1 s; 9 of 11 perturbed starts and 15 of 20 with its own gains +-3 % succeed, below the 9 of 10 bar (landings on the 0.9 m podium). In realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Jump the sweeper: standing on your podium, jump over the padded boom each time it sweeps round, 3 times in a row without being hit, then stand still on the podium. (Embodied Olympics `sweeper-jump`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Neither built-in gait can jump: the robot must jump with its feet above a boom almost as high as its knees, at the moment a fast boom arrives, and land on a small podium in balance, three times. Each landing has to be absorbed and the robot re-centred on the podium before the boom comes round again. The scene is dynamic (A motor-driven sweeper arm turns at rpm from t = 0.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference: walk, joint and lowcmd rows with the boom angle read privileged: it faces the boom, makes three tuck jumps with the soles 4-8 cm over the 0.30 m boom and stands 2 s, success at 21.1 s; 9 of 11 perturbed starts and 15 of 20 with its own gains +-3 % succeed, below the 9 of 10 bar (landings on the 0.9 m podium).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: You stand on a round podium, 0.9 m across and 0.4 m high, whose centre is 3.2 m from the axis of the motion base, facing the base. A foam boom 0.2 m thick, its axis 0.2 m above the podium's top, turns round the base counter-clockwise (seen from above) at 8.0 revolutions per minute, driven by a motor of at most 450.0 N m; it reaches 4.0 m from the axis, over the whole podium, and comes round once every 7.5 s. It is already turning at the start. A jump counts when the boom passes under both your feet while nothing of you touches anything (at the moment it passes each foot). You succeed when, after 3 counted jumps, your first contact is your feet on the podium and you then stand still for 1.0 s (only your feet on the podium, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s), before the boom comes round again. You fail at once if the boom touches any part of you (a hit; grabbing or holding it is a hit too), if any part of you touches the bed (the floor round the podium) or the motion base, if the boom passes through a foot that is not above it, on a fall (your pelvis less than 0.35 m above the podium's top, or any part of you other than your feet on the podium), on a landing after the last jump that is not on the feet, or after 30 s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | No official rule book exists: the sweeper is a party and amusement game, not a sport. The closest real device is Galaxy Multi Rides' 'Meltdown' (US Meltdown operator manual: an eight-player game, each player standing on a podium round a motion base whose foam booms spin round, 'the aim of the game is to either duck under, or jump over the boom as it spins around'; players must not grab, hold or ride the booms; a player who is hit is out; one 1 hp spin motor on a speed dial, at most 15.82 rpm; foam boom attachments 220 lb for the two booms; riders at least 48 in (1.22 m) tall and at most 200 lb), the same game as the 'Sweeper' of the TV show Wipeout. Its rules as played: stay on your podium, jump the low boom each time it comes round, the last player not hit wins; deviations: the booms: Meltdown's dual attachment has two foam booms; here there is only the low boom you jump (the duck boom is left off: this family tests the jump), so the rotor is that one boom, 50.0 kg, half of the attachment's 220 lb · the dimensions: the manual gives none of the boom's height, length or thickness, nor of the podiums. The boom's axis is 0.2 m above the podium's top, the mid-shin of a rider of the minimum height (1.22 m), its foam 0.2 m thick, reaching 4.0 m from the axis over the podiums of a 30 ft bed, whose centres are 3.2 m from the axis; each podium a 0.9 m disc 0.4 m high (reasonable sizes, not published ones) · the podium and the bed: the inflatable podium is a rigid platform and the inflatable bed a firm floor (neither's give is modelled; touching the bed is out anyway) · the speed: the operator's dial is set to a steady 8.0 rpm (about half the machine's top speed), already turning at the start; the machine's program, which changes speed, is not used · the count: one player, and a run of 3 jumps in a row with no hit is the success (a round number: the game has no count, its last player standing wins); after the last jump the robot must stand still for 1.0 s on its podium before the boom comes round again · a hit is any touch of the boom on the robot (in the game a light touch may leave a player standing); a jump is a pass of the boom under both feet while nothing of the robot touches anything · the motor: the 1 hp drive is a speed loop with a torque limit of 450.0 N m at the boom (1 hp at the top speed of 15.82 rpm, through the gearbox), no gearbox backlash or compliance; the foam's contact is a critically damped spring of 0.02 s time constant (an estimate for a soft polyurethane pad) |
| Stages | jump 1 → jump 2 → jump 3 → landing → stand |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.52 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
