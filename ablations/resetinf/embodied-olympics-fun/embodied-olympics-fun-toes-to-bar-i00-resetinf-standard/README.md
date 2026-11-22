# embodied-olympics-fun-toes-to-bar-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-toes-to-bar-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `toes_to_bar` / seed 0 |
| Oracle | `full` — Real reference solution (lowcmd rows, limp wrists, a slow strict fold; privileged state): a grid over the fold's angles gives the hips at -2.3 rad with straight knees (with the hips at the joint's limit and the knees bent the thighs meet the trunk 0.07 m short of the bar). Five repetitions in 46.7 s of the 60 s with the G1's own Dex3-1 hands at 1.5 times the device's drive torques (declared; the strict toes-to-bar needs 1.4 times: at 1.3 times a hand lets go in the fifth repetition); no arm or leg into the robot's own body; live, replay and the state hash agree. 6 of 6 variations succeed (servo gains x0.97 / x1.03 at hips -2.3 and -2.2 rad, both hip angles as they are; 46.7 to 51.0 s). The privileged twin's reference rows (4668 control steps, success after 46.68 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Hanging from the high bar by your two hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go. (Embodied Olympics `toes-to-bar`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The hands hold little more than your weight on the bar: a kip or a quick snap of the legs, and the feet striking the bar, pull harder than that, so the feet have to be brought up and lowered with little more than your weight on the bar. The bar is high above your pelvis and your legs are short: hip flexion alone does not bring the toes to the bar, the trunk has to lean back as well, against shoulders of 25 N m, five times within the time. The bar does not turn, so a twist of the hands on it is resisted by the same friction that holds you up. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Real reference solution (lowcmd rows, limp wrists, a slow strict fold; privileged state): a grid over the fold's angles gives the hips at -2.3 rad with straight knees (with the hips at the joint's limit and the knees bent the thighs meet the trunk 0.07 m short of the bar). Five repetitions in 46.7 s of the 60 s with the G1's own Dex3-1 hands at 1.5 times the device's drive torques (declared; the strict toes-to-bar needs 1.4 times: at 1.3 times a hand lets go in the fifth repetition); no arm or leg into the robot's own body; live, replay and the state hash agree. 6 of 6 variations succeed (servo gains x0.97 / x1.03 at hips -2.3 and -2.2 rad, both hip angles as they are; 46.7 to 51.0 s). The privileged twin's reference rows (4668 control steps, success after 46.68 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The bar is 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it is fixed and does not turn. Your hands are three-finger hands (a thumb, an index and a middle finger; their drives 1.5 times the stock hand's torques), and at the start each is closed round the bar; they hold it by their fingers' contact and friction only, so the bar can be torn out of a hand. A hand is on the bar while the bar touches any part of it (fingers, thumb or palm); when for more than 0.05 s a hand has not been on it, you have let go (whether you opened the hand or the bar was torn out), and there is no re-grip. Besides the hands only your legs may touch the bar: an arm, the trunk or the head on it fails. A repetition has two parts, in this order. The touch: both feet touch the bar at the same moment, each at a point between your two hands (their grasp centres; shins, knees or anything else of the legs on the bar is not a touch, and does not fail). The hang: afterwards the centres of both feet are at least 1.4 m below the bar and behind it (x less than the bar's; the heels back behind the bar), both at the same moment. You succeed when the hang of repetition 5 is reached. Swinging is allowed (a kip is legal), as is bending the knees on the way. You fail the moment you let go of the bar, an arm, the trunk or the head touches the bar, any part of you touches the uprights, the mats or the floor, or after 60 s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | CrossFit Games movement standard, toes-to-bar: from a full hang with the arms extended and the heels behind the bar, both feet touch the bar at the same time between the hands; kipping is allowed. The bar is the FIG horizontal bar (FIG Apparatus Norms: 2.80 m above the floor, 2.40 m between the uprights, 28 mm in diameter) over 0.20 m mats; deviations: the grip (the hands on the bar): each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index and middle 2 each, one motor per joint: 0.49 N m closing, 1.37 N m back-driven per finger joint), closed round the bar; it holds the bar by its fingers' contact and friction alone, nothing is welded, and the bar can be torn out of the hand; the bar is fixed, as the norm's is, and a hand turns on it only by sliding round it or by the wrist's joints · the grip (the hands stay on the bar): defined by contact: a hand is on the bar while the bar touches any part of it (fingers, thumb or palm: a hook grip counts); a break of up to 0.05 s (contacts flickering under a load) is not letting go · the grip force: the hands' drives are 1.5 times the Dex3-1's, because at the device's torques the two hands hold about one body weight on the bar (measured: the dead hang itself slips out within 3 s), at 1.5 times about 1.55 body weights (measured): 1.5 times is the hands' declared force margin over the device's rating. No Unitree hand is rated for this · CrossFit standard (the full hang is judged by eye: arms extended, heels behind the bar): the hang is judged by where the feet are (both feet's centres at least 1.4 m below the bar, about nine tenths of the dead hang's, and behind the bar), because the referee has positions, not a judge's eye · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, because the simulator has rigid bodies only |
| Stages | rep 1 → rep 2 → rep 3 → rep 4 → rep 5 |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
