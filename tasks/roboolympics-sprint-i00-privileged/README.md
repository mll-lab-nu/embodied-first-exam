# roboolympics-sprint-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-sprint-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sprint` / seed 0 |
| Oracle | `full` — Reference: stand through the start procedure, react to the gun, then the running policy at 3.5 m/s steered to the lane's centre; 9 of 10 perturbed runs at 2.5 to 4.0 m/s finished when it was written. Measured (make_oracles.py): success after 19.59 s of the 34.2 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Run the 50 m: wait for the starter's gun, then sprint down your lane until your torso reaches the finish line. (RoboOlympics `sprint`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The gun has to be seen, not guessed: moving early disqualifies and waiting costs time. Then 50 m in a 1.22 m lane: the walking gait covers 20 m in the time, the running gait has to be held straight for a quarter of a minute at a speed close to where it falls.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: stand through the start procedure, react to the gun, then the running policy at 3.5 m/s steered to the lane's centre; 9 of 10 perturbed runs at 2.5 to 4.0 m/s finished when it was written. Measured (make_oracles.py): success after 19.59 s of the 34.2 s limit, live and in a fresh replay, ending in the same state.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: World Athletics rules for the straight sprint. The lane runs along +x, 1.22 m wide, centred on y = 0. The start line is 0.05 m wide; its far edge is x = 0 and the finish line's near edge is x = 50.0 m. The start: "on your marks" at t = 0, "set" 2.0 s later, the gun between 1.2 and 2.2 s after "set" (fixed for this task, not announced). Your start movement is the first moment your pelvis is more than 0.05 m from where it was at "set", or the front end of a foot reaches the start line (x > -0.05 m, on the ground or in the air). A start movement before the gun, or earlier than 0.1 s after it, is a false start; so is a foot reaching the start line before "set". From the gun on you must keep your lane: your pelvis may not be more than half the lane's width from y = 0. You finish at the moment the leading point of your torso (not the head, arms, legs or feet) reaches the finish line; the time counts from the gun. You succeed with a valid finish within 30.0 s of robot time after the gun. A fall does not end the race: you are down while your pelvis is below 0.4 m, you may get up and run on, but 10.0 s down in a row end it. You fail on a false start, on leaving the lane, when down for 10.0 s, or when 30.0 s after the gun have passed.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 16 (the start: 16.5 the line, 16.6-16.8 false starts), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish, timing); the distance is the 50 m of indoor athletics; deviations: the distance: 50.0 m, the short sprint of indoor athletics, on an outdoor straight; not the 100 m · TR 16.3-16.4 (starting blocks, crouch start): a standing start without blocks, the feet 0.02 m behind the start line; a robot of this build has no crouch start · TR 16.6-16.8 (start information system): the start movement is measured on the robot instead of the blocks: the pelvis more than 0.05 m from its place at "set", or a foot reaching the start line; a false start disqualifies at once, there is no recall · TR 16 (the starter's voice and gun): the robot has no hearing; the commands are shown by a start lamp beside the lane (red, yellow at "set", green at the gun) · TR 17.3 (lanes): the lane is judged by the pelvis: its centre more than half a lane width from the lane's centre line disqualifies at once; feet on the lines are not judged · TR 17 (a fallen athlete): a robot whose pelvis is below 0.4 m is down; it may get up and run on, but 10.0 s down in a row end the race (did not finish) · TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches the plane of the finish line's near edge, interpolated between 1 ms physics steps · TR 14 (the track): a flat straight of three 1.22 m lanes, the robot alone in the middle one; no wind · a race has no time to beat; here the run counts only if it finishes within 30.0 s of robot time after the gun (this benchmark's qualifying time: a mean of about 1.7 m/s, beyond the walking gait) |
| Stages | start → finish |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `96f71984c3c44e5983033b13ecb2c762578edb53bc2a08e6f4ee39a25ee4c0a8` |
| Episode | 3420 control steps (34.2 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
