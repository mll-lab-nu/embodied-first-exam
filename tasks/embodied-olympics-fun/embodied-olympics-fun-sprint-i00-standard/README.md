# embodied-olympics-fun-sprint-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-sprint-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sprint` / seed 0 |
| Oracle | `full` — Reference: stand through the start procedure, react to the gun, then the running policy at 3.5 m/s steered to the lane's centre; 9 of 10 perturbed runs at 2.5 to 4.0 m/s finished when it was written. The privileged twin's reference rows (1959 control steps, success after 19.59 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Run the 50 m: wait for the starter's gun, then sprint down your lane until your torso reaches the finish line. (Embodied Olympics `sprint`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The gun has to be seen, not guessed: moving early disqualifies and waiting costs time. Then 50 m in a 1.22 m lane: the walking gait covers 20 m in the time, the running gait has to be held straight for a quarter of a minute at a speed close to where it falls. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Reference: stand through the start procedure, react to the gun, then the running policy at 3.5 m/s steered to the lane's centre; 9 of 10 perturbed runs at 2.5 to 4.0 m/s finished when it was written. The privileged twin's reference rows (1959 control steps, success after 19.59 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: World Athletics rules for the straight sprint. The lane runs along +x, 1.22 m wide, centred on y = 0. The start line is 0.05 m wide; its far edge is x = 0 and the finish line's near edge is x = 50.0 m. The start: "on your marks" at t = 0, "set" 2.0 s later, the gun between 1.2 and 2.2 s after "set" (fixed for this task, not announced). Your start movement is the first moment your pelvis is more than 0.05 m from where it was at "set", or the front end of a foot reaches the start line (x > -0.05 m, on the ground or in the air). A start movement before the gun, or earlier than 0.1 s after it, is a false start; so is a foot reaching the start line before "set". From the gun on you must keep your lane: your pelvis may not be more than half the lane's width from y = 0. You finish at the moment the leading point of your torso (not the head, arms, legs or feet) reaches the finish line; the time counts from the gun. You succeed with a valid finish within 30.0 s of robot time after the gun. A fall does not end the race: you are down while your pelvis is below 0.4 m, you may get up and run on, but 10.0 s down in a row end it. You fail on a false start, on leaving the lane, when down for 10.0 s, or when 30.0 s after the gun have passed.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 16 (the start: 16.5 the line, 16.6-16.8 false starts), TR 17.3 (lanes), TR 18.2 and TR 19 (the finish, timing); the distance is the 50 m of indoor athletics; deviations: the distance: 50.0 m, the short sprint of indoor athletics, on an outdoor straight; not the 100 m · TR 16.3-16.4 (starting blocks, crouch start): a standing start without blocks, the feet 0.02 m behind the start line; a robot of this build has no crouch start · TR 16.6-16.8 (start information system): the start movement is measured on the robot instead of the blocks: the pelvis more than 0.05 m from its place at "set", or a foot reaching the start line; a false start disqualifies at once, there is no recall · TR 16 (the starter's voice and gun): the robot has no hearing; the commands are shown by a start lamp beside the lane (red, yellow at "set", green at the gun) · TR 17.3 (lanes): the lane is judged by the pelvis: its centre more than half a lane width from the lane's centre line disqualifies at once; feet on the lines are not judged · TR 17 (a fallen athlete): a robot whose pelvis is below 0.4 m is down; it may get up and run on, but 10.0 s down in a row end the race (did not finish) · TR 19 (photo finish): the time is the instant the leading point of the torso link's collision mesh reaches the plane of the finish line's near edge, interpolated between 1 ms physics steps · TR 14 (the track): a flat straight of three 1.22 m lanes, the robot alone in the middle one; no wind · a race has no time to beat; here the run counts only if it finishes within 30.0 s of robot time after the gun (this benchmark's qualifying time: a mean of about 1.7 m/s, beyond the walking gait) |
| Stages | start → finish |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3420 control steps (34.2 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
