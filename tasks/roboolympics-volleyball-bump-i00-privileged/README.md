# roboolympics-volleyball-bump-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-volleyball-bump-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volleyball_bump` / seed 0 |
| Oracle | `full` — Reference: a walk to where the serve comes down, then a forearm platform on the walking policy, from a technique found offline by CMA-ES (RoboOlympics' method, search_technique.py): 11.4 m/s in, 7.3 m/s out, up to 3.08 m, down 0.13 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: the passive rebound, below net height, the body, a second touch, held, under the net, a net touch, over the centre line Measured (make_oracles.py): success after 5.81 s of the 10 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one contact, above net height and into the setter's target at the net. (RoboOlympics `volleyball-bump`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The arms have to be made into a platform 0.7 m to the side and in front of where the robot stands, within about four seconds of a walking policy that manages half a metre per second sideways, and angled so that an 11 m/s ball rebounds 2 m up and 5 m forward into a 2 m circle: a few degrees of platform angle are a metre at the target.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: a walk to where the serve comes down, then a forearm platform on the walking policy, from a technique found offline by CMA-ES (RoboOlympics' method, search_technique.py): 11.4 m/s in, 7.3 m/s out, up to 3.08 m, down 0.13 m from the target's centre. Open loop on the frozen start, not robust. Referee test negatives: the passive rebound, below net height, the body, a second touch, held, under the net, a net touch, over the centre line Measured (make_oracles.py): success after 5.81 s of the 10 s limit, live and in a fresh replay, ending in the same state.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: You stand in your own half of an official volleyball court (9.0 m by 9.0 m on each side of the net), facing the net, 6.0 m from it, midway between the side lines. The net's top is 2.43 m high. A volleyball (0.21 m across, 0.27 kg, in air) is served over the net from behind the far end line 3.0 s after the start: a float serve, without spin, that comes down in your part of the court. The pass is the ball's first contact after the serve, on your side of the net and before it touches the floor: with your forearms or hands (one arm or both; the arm from the elbow down), all contacts within 0.1 s, over when the ball has been clear of you for 0.03 s. After it the ball's centre must rise above the height of the net's top, and the ball must come down in the setter's target: its first contact with the floor is inside a circle of 1.0 m radius whose centre is 1.0 m from the net on your side and 1.5 m to the right of the court's middle (to your right as you face the net). That is the success. You fail if the ball touches the floor before your pass, if any part of you other than a forearm or a hand touches the ball, if the pass's contacts last longer than 0.1 s (the ball held), if you touch the ball again after the pass, if you touch the ball before it has crossed the net, if the ball comes down outside the target or without having risen above the net's height, if you touch the net, an antenna or a post, if a foot of yours is on the floor wholly beyond the centre line, if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 10 s. The ball cannot be gripped, and it cannot be touched while it waits to be served.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | FIVB Official Volleyball Rules 2025-2028: Rule 1 (the court 18 m x 9 m, the attack lines 3 m from the centre line), Rule 2 (the men's net, top at 2.43 m, the antennas), Rule 3 (the ball: 65-67 cm round, 260-280 g), Rule 9.2 (the hit: the ball may touch any part of the body, it must not be caught or thrown), Rule 11 (no contact with the net, the foot not wholly beyond the centre line), Rule 14.5 (the serve may not be blocked); deviations: Rule 12 (the service): the serve is a scripted launch, a float serve (no spin) of about 14 m/s from 0.6 m behind the far end line, the same in every attempt, instead of an opponent; the ball follows MuJoCo's drag model, without a float serve's sideways wobble. · Rule 9.2 lets a team-mate play the ball next; here nobody does, and a good reception is defined as volleyball coaching grades it: the pass rises above the net's height and comes down in the setter's target, a circle of 1.0 m radius 1.0 m from the net between positions 2 and 3, judged where the ball first touches the floor. · The family asks for the forearm pass: only the forearms and the hands (the arm from the elbow down) may touch the ball, where Rule 9.2.1 allows any part of the body. 'Not caught or thrown' is a contact of at most 0.1 s (the ball cannot be gripped). · No team-mates or opponents, no wind. |
| Stages | pass → above the net height → in the target |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `cd8ddefcf6cc73ec07e3046d56371b714e7a094966cf11fd5d77932bcdc0bb57` |
| Episode | 1000 control steps (10 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
