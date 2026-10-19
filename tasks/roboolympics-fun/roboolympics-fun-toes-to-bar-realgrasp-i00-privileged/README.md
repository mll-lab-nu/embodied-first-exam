# roboolympics-fun-toes-to-bar-realgrasp-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | privileged |
| Twin | `roboolympics-fun-toes-to-bar-realgrasp-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `toes_to_bar_realgrasp` / seed 0 |
| Oracle | `full` — Reference: a slow strict toes-to-bar (3 s fold, gentle touch, 5.5 s leg return, swing damped between reps) within the Dex1-1's 238 N-per-hand friction: 5 repetitions in 39.2 s; 9 of 10 perturbed starts (37-40 s). The base's kipped snap tears the bar out of the jaws. Measured (make_oracles.py): success after 39.17 s of the 60 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Hanging from the high bar by the two grippers that are your hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go. (RoboOlympics `toes-to-bar-realgrasp`: one Unitree G1 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The grippers' friction holds about 1.4 times your weight in all, and the bar never slides back in: a kip or a quick snap of the legs, and the feet striking the bar, pull harder than that, so the feet have to be brought up and lowered with little more than your weight on the bar. The bar is 0.84 m above your pelvis and your legs are 0.75 m long: hip flexion alone does not bring the toes to the bar, the trunk has to lean back as well, against shoulders of 25 N m, five times within the time.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: a slow strict toes-to-bar (3 s fold, gentle touch, 5.5 s leg return, swing damped between reps) within the Dex1-1's 238 N-per-hand friction: 5 repetitions in 39.2 s; 9 of 10 perturbed starts (37-40 s). The base's kipped snap tears the bar out of the jaws. Measured (make_oracles.py): success after 39.17 s of the 60 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The bar is 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it turns freely about its own axis. Your hands are two-finger grippers, and at the start each is closed on the bar; they hold it by the friction of their jaws only, so the bar can slide along the jaws and out of them. A hand holds the bar while the bar touches both of that gripper's jaws; when for more than 0.05 s a hand has not held it, you have let go (whether you opened the gripper or the bar slipped out), and there is no re-grip. Besides the grippers only your legs may touch the bar: an arm, the trunk or the head on it fails. A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each at a point between your two hands (the jaws' centres; shins, knees or anything else of the legs on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet are at least 1.4 m below the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment (in your dead hang they are 1.59 m below it). You succeed when the hang of repetition 5 is reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment you let go of the bar, an arm, the trunk or the head touches the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

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
| Category | parkour-apparatus-balance |
| Rule book | CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the uprights, 28 mm in diameter) over 0.20 m mats; deviations: the grip (the hands on the bar): each hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws with rubber pads, at most 120 N; sold for the G1), closed across the bar; it holds the bar by the jaws' friction alone, nothing is welded, and the bar can slide along the jaws and out of them. Flat jaws clamp the bar but cannot wrap round it, so the bar turns freely in its bearings about its own axis in place of the hands turning round a fixed bar · the grip (the hands stay on the bar): defined by contact: a hand holds the bar while the bar touches both of its gripper's jaws; a break of up to 0.05 s (the pads' contact flickering under a load; measured breaks last 1 to 3 ms) is not letting go · CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged by where the feet are (both feet's centres at least 1.4 m below the bar, toes-to-bar's nine tenths of its dead hang's 1.55 m, and behind the bar), because the referee has positions, not a judge's eye · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies only |
| Stages | rep 1 → rep 2 → rep 3 → rep 4 → rep 5 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `4e6beefe739ee3d6e4a6756ae72dce370e63aa26acada92bbbb37b622eca9fa8` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/roboolympics-fun-files/, built from embodied_first_exam/roboolympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
