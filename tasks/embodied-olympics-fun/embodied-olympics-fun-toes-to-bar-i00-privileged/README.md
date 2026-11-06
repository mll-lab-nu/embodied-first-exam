# embodied-olympics-fun-toes-to-bar-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-toes-to-bar-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `toes_to_bar` / seed 0 |
| Oracle | `full` — Real reference solution (lowcmd rows, limp wrists, a slow strict fold; privileged state): a grid over the fold's angles gives the hips at -2.3 rad with straight knees (with the hips at the joint's limit and the knees bent the thighs meet the trunk 0.07 m short of the bar). Five repetitions in 46.7 s of the 60 s with the G1's own Dex3-1 hands at 1.5 times the device's drive torques (declared; the strict toes-to-bar needs 1.4 times: at 1.3 times a hand lets go in the fifth repetition); no arm or leg into the robot's own body; live, replay and the state hash agree. 6 of 6 variations succeed (servo gains x0.97 / x1.03 at hips -2.3 and -2.2 rad, both hip angles as they are; 46.7 to 51.0 s). Measured: success after 46.68 s of the 60 s limit, live and in a fresh replay, ending in the same state. The grip scale's need: the strict toes-to-bar of the reference solution needs 1.4 times the Dex3-1's drive torques (1.3 times lets go in the fifth repetition). |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Hanging from the high bar by your two hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go. (Embodied Olympics `toes-to-bar`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The hands hold little more than your weight on the bar: a kip or a quick snap of the legs, and the feet striking the bar, pull harder than that, so the feet have to be brought up and lowered with little more than your weight on the bar. The bar is high above your pelvis and your legs are short: hip flexion alone does not bring the toes to the bar, the trunk has to lean back as well, against shoulders of 25 N m, five times within the time. The bar does not turn, so a twist of the hands on it is resisted by the same friction that holds you up.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Real reference solution (lowcmd rows, limp wrists, a slow strict fold; privileged state): a grid over the fold's angles gives the hips at -2.3 rad with straight knees (with the hips at the joint's limit and the knees bent the thighs meet the trunk 0.07 m short of the bar). Five repetitions in 46.7 s of the 60 s with the G1's own Dex3-1 hands at 1.5 times the device's drive torques (declared; the strict toes-to-bar needs 1.4 times: at 1.3 times a hand lets go in the fifth repetition); no arm or leg into the robot's own body; live, replay and the state hash agree. 6 of 6 variations succeed (servo gains x0.97 / x1.03 at hips -2.3 and -2.2 rad, both hip angles as they are; 46.7 to 51.0 s). Measured: success after 46.68 s of the 60 s limit, live and in a fresh replay, ending in the same state. The grip scale's need: the strict toes-to-bar of the reference solution needs 1.4 times the Dex3-1's drive torques (1.3 times lets go in the fifth repetition).

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: The bar is 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it is fixed and does not turn. Your hands are three-finger hands (a thumb, an index and a middle finger; their drives 1.5 times the stock hand's torques), and at the start each is closed round the bar; they hold it by their fingers' contact and friction only, so the bar can be torn out of a hand. A hand is on the bar while the bar touches any part of it (fingers, thumb or palm); when for more than 0.05 s a hand has not been on it, you have let go (whether you opened the hand or the bar was torn out), and there is no re-grip. Besides the hands only your legs may touch the bar: an arm, the trunk or the head on it fails. A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each at a point between your two hands (their grasp centres; shins, knees or anything else of the legs on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet are at least 1.4 m below the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment. You succeed when the hang of repetition 5 is reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment you let go of the bar, an arm, the trunk or the head touches the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

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
| Rule book | CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the uprights, 28 mm in diameter) over 0.20 m mats; deviations: the grip (the hands on the bar): each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index and middle 2 each, one motor per joint: 0.49 N m closing, 1.37 N m back-driven per finger joint), closed round the bar; it holds the bar by its fingers' contact and friction alone, nothing is welded, and the bar can be torn out of the hand; the bar is fixed, as the norm's is, and a hand turns on it only by sliding round it or by the wrist's joints · the grip (the hands stay on the bar): defined by contact: a hand is on the bar while the bar touches any part of it (fingers, thumb or palm: a hook grip counts); a break of up to 0.05 s (contacts flickering under a load) is not letting go · the grip force: the hands' drives are 1.5 times the Dex3-1's, because at the device's torques the two hands hold about one body weight on the bar (measured: the dead hang itself slips out within 3 s), at 1.5 times about 1.55 body weights (measured): 1.5 times is the hands' declared force margin over the device's rating. No Unitree hand is rated for this · CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged by where the feet are (both feet's centres at least 1.4 m below the bar, about nine tenths of the dead hang's, and behind the bar), because the referee has positions, not a judge's eye · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies only |
| Stages | rep 1 → rep 2 → rep 3 → rep 4 → rep 5 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `75b3d769d26c912b73f20f21d85a73e7b5534420187cd856928f468962b5f50a` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
