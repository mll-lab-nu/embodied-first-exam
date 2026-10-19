# roboolympics-fun-long-rope-i00-standard-realtime

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `roboolympics-fun-long-rope-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `long_rope` / seed 0 |
| Oracle | `full` — Reference: a periodic hop from a balanced crouch (joints/lowcmd rows) timed to the rope's angle, closed loop on privileged rope and pelvis state: 10 consecutive jumps, the rope 4-9 cm under the soles, lands at 10.17 s and stands 0.5 s before the still-turning rope comes round (success 10.85 s); 10 of 10 under small perturbations of the rope's phase and tempo and a push at the start; 48 of 50 with its own lead and push gain varied (push gain +3 %: 8 of 10). Also an injected positive (2.0 m/s kicks 0.18 s before each pass). Negatives: standing still, a late or low hop, a squat, leaving the centre zone, lying down, a tipping jump, a bad last landing, no stand after the landing; two hops per turn count once. In standard-realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S (board 0112). |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Jump the long rope: standing in the middle of a rope turned by two turners, jump it 10 times in a row, the rope passing under both your feet while you are in the air, without the rope ever touching you. (RoboOlympics `long-rope`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Neither built-in gait can jump: the robot must hop again and again, in time with a rope it has to watch, with its feet off the ground at the very moment the rope passes and back on balance before the next turn. Each landing must be absorbed while the next take-off is already being prepared, and any drift out of the middle or a toe left behind catches the rope. The scene is dynamic (`scripts/task_dynamics.toml`: Two scripted turners turn the rope from t = 0 at tempo_rev_s.), and in standard-realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 10 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference: a periodic hop from a balanced crouch (joints/lowcmd rows) timed to the rope's angle, closed loop on privileged rope and pelvis state: 10 consecutive jumps, the rope 4-9 cm under the soles, lands at 10.17 s and stands 0.5 s before the still-turning rope comes round (success 10.85 s); 10 of 10 under small perturbations of the rope's phase and tempo and a push at the start; 48 of 50 with its own lead and push gain varied (push gain +3 %: 8 of 10). Also an injected positive (2.0 m/s kicks 0.18 s before each pass). Negatives: standing still, a late or low hop, a squat, leaving the centre zone, lying down, a tipping jump, a bad last landing, no stand after the landing; two hops per turn count once.

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17, board 0151); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: Two turners stand 3.6 m apart, one on each side of you (on the y axis, at y = -1.8 and +1.8 m); they turn a 6.0 m rope, 0.01 m thick, holding it 1.4 m from each end, at a steady 1.0 revolutions per second: each hand goes round a vertical circle of 0.4 m radius, 1.0 m above the floor, 0.4 m in front of its turner. The rope goes over your head from behind you to the front, down in front of you and under you towards your back; it is already turning at the start. A jump counts when the rope passes under both your feet while nothing of you touches the ground (at the moment it passes under each foot), after it has passed over your head since the last counted jump (one jump per turn of the rope). You succeed when, after 10 counted jumps, the first contact with the floor is your feet only and you then stand still for 0.5 s (only your feet on the floor, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s): the turners keep turning, so this has to be done before the rope comes round again, and it must not touch you until then. You fail at once if the rope touches any part of you (a miss: the turners do not stop), if your pelvis leaves the centre zone (within 0.5 m of the rope's axis forwards and backwards and 0.5 m of the middle between the turners sideways), if the rope passes under a foot that is on the ground or through you, on a fall (your pelvis lower than 0.35 m, or any part of you other than your feet on the ground), on a landing that is not on the feet after the last jump, or after 20 s.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: as the standard twin; the GPU renders the cameras over EGL (board 0112, 2026-10-14): author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | The Asian Jump Rope Union's AC2026 Asian Long Rope Championship Rules (AJRU, IJRU's continental body): event #2 '8 Jumpers' (two turners turn one long rope, the jumpers jump it together; the rope must pass under the feet of the jumpers to score 1 point) with the turners 3.6 m apart, the distance event #1 'Figure 8' sets (event #2 sets none); the common rules (the rope remains still until the start signal; leaving the event area is a space violation); and the IJRU Judging Manual (show freestyle, long rope): a long rope is at least 6.0 m long; deviations: 8 Jumpers: one jumper (the robot) instead of eight, and a count of consecutive jumps, 10 in a row with no miss, instead of the jumps in 1 minute; the count is the benchmark's qualifying mark, a round number (school long-rope practice counts runs of consecutive jumps; no rule book sets this one) · the turners are scripted, not athletes: each holds the rope 1.4 m from its end, the rest wound round the hand, so that the free rope between the hands (3.2 m) just brushes the floor under the jumper (as turners shorten a long rope to the jumpers); each moves the hand on a vertical circle of 0.4 m radius whose centre is 1.0 m high and 0.4 m in front of the turner, at a steady 1.0 revolutions per second; they never adapt to the jumper, and they do not stop when the rope is caught (the rope's ends beyond the hands are not modelled) · the start: the rope is already turning at the start (t = 0), not still until a signal; its lowest part has just passed under the robot, going backwards · the end: the event has none (the clock stops the round); here the robot must land on its feet after the last jump and stand still for 0.5 s, all before the still-turning rope comes round again (a longer stand would need the turners to stop the rope, and a stopping rope swings on into the jumper) · a miss is any touch of the rope on the robot (the rules only score the passes); a jump is a pass of the rope under both feet while nothing of the robot touches the ground, and the robot must stay in the middle of the rope (the centre zone) instead of the event's space rule · the rope: a 0.01 m cotton rope of 0.06 kg/m (a typical 10 mm braided cotton rope) modelled as a chain of 40 short capsules joined end to end by stiff point constraints (free to bend and twist: a cord has almost no bending stiffness), in still air with its drag; no wind |
| Stages | jump 1 → jump 2 → jump 3 → jump 4 → jump 5 → jump 6 → jump 7 → jump 8 → jump 9 → jump 10 → landing → stand |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 1.82 with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 attempts; ws-1, 4 CPUs, board 0163, 2026-10-18); PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 10 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
