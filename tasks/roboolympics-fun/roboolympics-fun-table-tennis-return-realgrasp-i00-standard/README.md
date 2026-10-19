# roboolympics-fun-table-tennis-return-realgrasp-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-table-tennis-return-realgrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `table_tennis_return_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_table_tennis_return_realgrasp.py: positive by injection (robot put at the end line) with a real stroke holding the free paddle at 120 N: returned 0.73 m past the net, 9/10 placements; negatives as table-tennis-return plus racket dropped/thrown/out of hand, held by the blade, against the thigh, racket in the net; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Return the service: after the table tennis ball has bounced once on your court, strike it with the paddle held in your right hand's gripper so that it touches the opponent's court, without letting go of the paddle. (RoboOlympics `table-tennis-return-realgrasp`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The served ball is over your court for a few tenths of a second, low above a table that is as high as your hips, and may have to be met far inside the end line: the blade, a rigid extension of a 0.5 m arm, has to be there at the right instant and angle while the body leans over the table without touching the net. The return must clear a 15 cm net and still come down on a court 1.37 m long, off a ball that carries spin. The paddle sits in a two-finger gripper: the blade is where the jaws hold it, and a fast stroke must not fling it out of the hand. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-table-tennis-return-realgrasp-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The table is the official one: 2.74 m long, 1.525 m wide, its playing surface 0.76 m above the floor, with a net 0.1525 m high across its middle that reaches 0.1525 m beyond each side line. Your court is the half of the playing surface on your side of the net, the opponent's court the other half; the top edges belong to the playing surface, the sides of the table top do not (a ball that touches the table with its centre below the level of the playing surface has hit the side). The ball is the official one (40 mm, 2.7 g) and flies in air: drag and the lift of its spin act on it. The racket is a separate body: a rigid square blade 0.15 m wide and 0.015 m thick on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick, 0.14 kg in all, the blade's centre 0.175 m from the butt. At the start its handle is closed in your right hand's two-finger gripper, which holds it by friction only: it can slip, turn in the gripper and fall. Your right hand (the gripper's jaws and body) is the racket hand, your left hand the free hand. The racket is in your hand while its handle touches both of the gripper's jaws; it has left your hand when for more than 0.05 s the handle has not touched both jaws. The service is struck 3.0 s after the start: a legal service, so the ball bounces first on the server's court, passes the net and bounces on your court. Then you must make a good return (Law 2.7): strike the ball, after that one bounce on your court, with the blade of the racket in your hand or with the racket hand below the wrist (the gripper), so that it touches the opponent's court, directly or after touching the net; it may pass over or around the net. You succeed at the moment the ball touches the opponent's court after your strike. All contacts of the blade or the racket hand with the ball within 0.05 s of the first are one strike. You fail if the racket leaves your hand at any time (dropped, thrown or slipped out of the gripper); if the racket touches any part of you other than the racket hand; if you or the racket touch the ball before the service, or before it has bounced on your court (obstruction); if the ball bounces a second time on your court before you strike it (ball contacts with the table less than 0.02 s apart are one bounce); if anything other than the blade or the racket hand touches the ball (the racket's handle, an arm, the body); if the blade or the racket hand touches the ball again later than 0.05 s after the first contact (struck twice, or carried); if after your strike the ball touches your own court, the side of the table or the floor before the opponent's court; if the ball touches the floor at any time; if any part of you or the racket touches the net; if the racket touches the floor; if your free hand touches the playing surface while the ball is in play (from the service on); if you fall; or after 8 s. Anything else of you, the racket included, may touch the table. A fall is your pelvis lower than 0.35 m above the floor, or any part of you other than your feet touching the floor. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | basketball-and-rackets |
| Rule book | ITTF Handbook 2024, The Laws of Table Tennis: 2.1 (the table), 2.2 (the net assembly), 2.3 (the ball), 2.4 (the racket), 2.5 (definitions: struck, obstruction, racket hand, free hand), 2.6 (the service), 2.7 (the return), 2.10 (a point); deviations: 2.6.1-2.6.3 (the service): there is no server and no toss: the ball waits at the server's strike point and is launched at 3.0 s with the position, velocity and spin it has at the strike of a legal service of RoboOlympics' serve library (a service a Franka arm made under its real limits; entry 221, the draw of this instance's seed, not chosen for being returnable), because the task is one return, not a match · 2.1.3 (the table's bounce): the playing surface is Google DeepMind's system-identified table, on which a ball dropped from 30 cm rebounds 26 cm, not the Law's about 23 cm; it is the only identified model of the ball's bounce with spin there is · 2.2 (the net): the net is a rigid wall 1 cm thick, 0.1525 m high, reaching 0.1525 m beyond each side line, without separate posts or a cord (DeepMind's model); a soft net is not simulated · 2.4 (the racket): the blade is a rigid 15 cm square, 1.5 cm thick, on a straight handle 0.1 m long, 0.032 m wide and 0.025 m thick, 0.14 kg in all (legal: the Laws set no size, shape or weight); its covering is one contact law on both faces (RoboOlympics' ball-paddle pair, hand-picked, not identified) · 2.5.5 (the racket hand, the hand carrying the racket): the hand is a two-finger gripper, Unitree's Dex1-1 (90 mm stroke, 80 mm jaws, at most 120 N); the handle lies along its jaws and the racket is held by their friction alone, as a hand holds it; "carrying" is defined by contact: the handle touches both of the gripper's jaws, and a break of up to 0.05 s is not a release; the racket may touch nothing of the player but the racket hand (the Laws do not forbid a second hand on the racket; here it would make the free hand a second racket hand) · 2.10.1.7 (deliberately striking the ball twice): intent cannot be judged: every contact of the blade or the racket hand within 0.05 s of the first is the same strike, a later one is a second strike · 2.10.1.8 (moving the playing surface): the table is fixed and this is not judged: a competition table weighs three times the robot and more, and the robot's push on it is limited by the grip of its own feet · 2.5.8 and 2.10.1 (the ball touching the player): any touch of the ball by anything but the blade or the racket hand loses the point, also after the ball has bounced on the robot's court (stricter than the Laws, which then only require that the return be struck) |
| Stages | bounce → strike → opponent's court |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 800 control steps (8 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
