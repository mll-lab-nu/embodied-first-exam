# roboolympics-shot-put-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-shot-put-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `shot_put` / seed 0 |
| Oracle | `full` — Reference: a standing put from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 8.1 m/s from 1.78 m, pushed (0.997), 8.20 m (the line is 6 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test: positive by injection; negatives: the shot lowered, taken behind the shoulders, a sling, the other hand, out early, toes on the board, outside the sector, short, a front-half exit Measured (make_oracles.py): success after 6.08 s of the 60 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` |

## Task
Put the shot that your right hand holds at your neck, from the shoulder with that hand alone, so that it lands inside the sector at least 6.0 m from the circle, then leave the circle from its rear half and stand. (RoboOlympics `shot-put`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The shot weighs 7.26 kg and the H1-2's arm motors give 40 N m at the shoulder and 18 N m at the elbow: the arm alone cannot push it fast, so the legs and the trunk have to drive the put, inside a circle two steps wide. 6.0 m needs a release near 7 m/s at about 40 degrees. The stance you start in is not in balance under the shot: held as it is in `stand` mode the robot topples forward within about 4.5 s, so the put (or a counter-lean) has to begin at once.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: a standing put from a technique found offline by CMA-ES over whole-body key poses (RoboOlympics' method, search_technique.py): 8.1 m/s from 1.78 m, pushed (0.997), 8.20 m (the line is 6 m), then out of the rear half and standing. Open loop on the frozen start, not robust. Referee test: positive by injection; negatives: the shot lowered, taken behind the shoulders, a sling, the other hand, out early, toes on the board, outside the sector, short, a front-half exit Measured (make_oracles.py): success after 6.08 s of the 60 s limit, live and in a fresh replay, ending in the same state.

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The men's shot (7.26 kg, 0.12 m across) starts gripped against your right palm beside your neck: you have taken your stance. The circle is 2.135 m across inside its rim; the ground outside is 0.02 m higher than its inside. At the front, a stop board 1.21 m long, 0.112 m wide and 0.1 m high follows the rim. The sector opens from the circle's centre, 34.92 degrees wide, symmetric about the direction you face at the start. The put (TR 33.1), judged on the shot's centre relative to your trunk (the line through your two shoulder joints, your trunk's up and forward directions) from the start to the release: the centre never lower than 0.0 m below the line of the shoulders and never more than 0.0 m behind it; nothing but your right hand and your trunk touches the shot; and when you let go (once: it cannot be gripped again) the shot must be moving away from your right shoulder joint with at least 0.5 of its speed relative to that joint (a push from the shoulder, not a throw or a sling). The shot's first touch of the ground must be inside the sector lines (on a line is out); the put is measured from that point to the inside of the rim along the line through the circle's centre. You succeed when a valid put measures at least 6.0 m and you have then left the circle correctly and stood for 1.0 s. Leaving correctly: after the shot has landed, your first touch of the rim's top or of the ground outside the circle is behind the line through the circle's centre across the putting direction (the rear half). Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if any part of you touches the rim's top (its top inside edge included), the ground outside the circle or any part of the stop board other than its inner side (its top edge is not its inner side) before the shot has landed, or in the front half before you have left correctly; if the shot drops below or goes behind the line of the shoulders, is touched by anything but the right hand and the trunk, or is not pushed at the release; if it lands outside the sector or short of 6.0 m; if any part of you touches it after the release (your right arm and your trunk may still brush it during the first 0.2 s); if you fall (your pelvis lower than 0.5 m above the circle's floor, or any part of you other than your feet on the ground); or after 60 s. Where you touch the ground is judged on the points of contact; a contact within 0.003 m of the rim's top, or that far outside the stop board's inner side, counts as on the top. The neck line of the stance runs from 0.08 m above the middle of the shoulder line to the chin, 0.2 m above and 0.09 m in front of it; at the start the shot's centre is within 0.22 m of it.

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
| Category | throwing-catching-striking |
| Rule book | World Athletics Competition and Technical Rules 2024: TR 32.5-32.8 (the circle), TR 32.12 (the sector), TR 32.13, 32.14, 32.16, 32.17 and 32.20 (throwing events: the start, failures, the landing, leaving the circle, the measurement), TR 33.1 (the put from the shoulder), TR 33.2 (the stop board), TR 33.4-33.5 (the men's shot); deviations: TR 33.1 ("touch or be in close proximity to the neck or the chin"): the hand holds the shot by a grip switched on and off; the stance is given at the start (the shot against the palm beside the neck, its centre within 0.22 m of the line from the base of the neck to the chin). From then to the release the rule is judged on the shot's centre in the trunk's frame: "the hand shall not be dropped below this position" as not lower than 0.0 m below the line of the two shoulder joints, "not behind the line of the shoulders" as not more than 0.0 m behind that line, and "put" (not thrown or slung) as: at the release the shot moves away from the putting shoulder's joint with at least 0.5 of its speed relative to that joint. · TR 32.5-32.6: the ground outside the circle is level with the rim's top for 1 m and then falls to the field's level over 1 m (the circle's inside is the field's level, 0.02 m below the rim, instead of the field being level with the rim). · TR 32.20: the mark is the point where the shot first touches the ground, not the nearest edge of its dent. · TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the put, and the shot cannot be gripped again. · TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the trial ends when the robot has left the circle correctly and stands. · TR 25.17 (one minute for a trial): the whole trial, leaving the circle included, has 60 s. · Flight: the shot's drag in still air (MuJoCo's ellipsoid fluid model, a quasi-steady model), no wind. · The qualifying mark of 6.0 m is this benchmark's (a school standard for the 7.26 kg shot); the rule book only measures. |
| Stages | release → landing → exit |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `537db73c96b750758a268c415a1db896f44d0bbdf79f4ff71c4230f9039757d9` |
| Episode | 6000 control steps (60 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
