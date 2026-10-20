# embodied-olympics-fun-paddle-bounce-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-paddle-bounce-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `paddle_bounce` / seed 0 |
| Oracle | `full` — Reference: the paddle kept level under the ball and tapped up at each bounce, closed loop on the ball's state: 20 bounces, each back to the drop height; 11 of 11 perturbations when it was written. A still blade gets 6 to 13 bounces of the 0.15 m rise alone, which is why each bounce must also reach the drop height. Measured: success after 14.53 s of the 20 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Keep the table tennis ball that is dropped in front of you bouncing on the paddle in your right hand: 20 bounces in a row, each back up to the height the ball was dropped from. (Embodied Olympics `paddle-bounce`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Every bounce needs an upward hit of the right strength at the right instant, with the blade level and under a 40 mm ball: a tilt of a degree sends the ball off the 15 cm blade within a few bounces, and the arm that holds the blade gives way a little at every hit. It has to go right twenty times in a row.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: the paddle kept level under the ball and tapped up at each bounce, closed loop on the ball's state: 20 bounces, each back to the drop height; 11 of 11 perturbations when it was written. A still blade gets 6 to 13 bounces of the 0.15 m rise alone, which is why each bounce must also reach the drop height. Measured: success after 14.53 s of the 20 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A table tennis racket (a rigid square blade 0.15 m wide and 0.015 m thick on a short handle, 0.14 kg) is fixed to your right hand. The official ball (40 mm, 2.7 g; it flies in air, with drag) hangs at rest, its centre 1.2 m above the floor, until 2.0 s after the start, and then falls. You succeed after 20 bounces in a row on the blade (either face; the faces need not alternate). A bounce is a touch of the blade after which, before the ball touches the blade again, the ball's centre rises at least 0.15 m above the height at which it left the blade and reaches at least the height it was dropped from, 1.2 m above the floor, and which the ball leaves with at least 0.98 of the speed it reached the blade with (both speeds taken at the height where the touch began). On a still blade every bounce is lower than the one before (the ball keeps about nine tenths of its height, 0.95 of its speed), so each bounce needs a hit of the blade; a rebound that rises enough but was not hit is not counted, and is not a fault. A touch is all contact of the ball with the blade from the first contact on, with breaks shorter than 0.02 s; a bounce's own contact lasts about a millisecond. You fail if the ball comes back to the blade after a touch without having risen that much; if a touch lasts longer than 0.02 s from its first contact to its last (the ball rests, rolls or is carried on the blade); if the ball touches the floor or anything of yours other than the blade (the racket's handle, the hand and the arm included); if you touch the ball before it is dropped; if you fall; or after 20 s. A fall is your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor (the racket on the floor is a fall).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | basketball-and-rackets |
| Rule book | ITTF Handbook 2024, The Laws of Table Tennis, for the equipment: 2.3 (the ball), 2.4 (the racket). Bouncing the ball on the racket is a ball-control drill, not an event with a rule book: the number of consecutive bounces asked for is this benchmark's line; deviations: 2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, 0.14 kg with its handle (legal: the Laws set no size, shape or weight); its covering is one contact law on both faces (Embodied Olympics' ball-paddle pair, hand-picked, not identified), and it is fixed to the right hand, because the robot's fist cannot hold a handle · the start: nobody hands the robot a ball; it hangs at rest in front of the robot and is let go at 2.0 s · a bounce is a hit: so that the rebounds of one strong hit off a still blade are not counted, the ball must leave a counted bounce with at least 0.98 of the speed it reached the blade with (both taken at the height of the touch; a still blade returns about 0.95); a bounce that does not is not counted, and is not a fault |
| Stages | bounce 1 → bounce 2 → bounce 3 → bounce 4 → bounce 5 → bounce 6 → bounce 7 → bounce 8 → bounce 9 → bounce 10 → bounce 11 → bounce 12 → bounce 13 → bounce 14 → bounce 15 → bounce 16 → bounce 17 → bounce 18 → bounce 19 → bounce 20 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `1ec955cace61b6f279b909c4b5b260620da2b9a5e5ca6235d9d25b135548227e` |
| Episode | 2000 control steps (20 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
