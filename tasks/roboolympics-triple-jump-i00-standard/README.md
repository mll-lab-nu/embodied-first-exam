# roboolympics-triple-jump-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-triple-jump-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `triple_jump` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_triple_jump.py: positive by injection (three take-offs with the legs swapped in the air by the robot's own motors: hop 2.64 m, step 5.87 m, mark 8.65 m); negatives: a foot over the line, a two-foot hop, the hop or the step on the wrong foot, another part on the ground, the landing foot down again half a metre on (travelling between two phases), not into the sand. No single-leg take-off exists for this robot; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Do a triple jump: run up, hop from behind the take-off line and land on the same foot, step onto the other foot, and jump from it into the sand pit. (RoboOlympics `triple-jump`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Seven metres in three flights, each from one foot: every phase has to be more than twice this robot's best published two-foot jump, taken from a single leg, and landed on a single leg with enough balance and speed left to take off again. Nothing built in hops on one foot at all. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-triple-jump-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: World Athletics rules for the triple jump. The runway is 40.0 m long and 1.22 m wide along +x and goes on to the pit. The take-off line is x = 0, the edge of the white take-off board (0.2 m long) that is nearer the pit. The landing area is a pit of sand, level with the runway, that begins 7.0 m beyond the take-off line and is 9.0 m long and 2.75 m wide, centred on y = 0. A flight is a time of at least 0.05 s in which nothing of you touches anything. Until the hop: no foot that is on the ground may have any part of it on or over the take-off line's plane (the whole foot counts, also the parts of it that are in the air), and nothing of you may touch the ground at x >= 0. (1) The hop is the flight that ends with your first contact beyond the line. It must be taken off from one foot within the runway's width: the other foot has left the ground at least 0.05 s before the take-off foot; your pelvis must rise at least 0.05 m above its height at lift-off; and its first contact must be the take-off foot alone, on the runway. (2) The step is the next flight: until it starts only the foot you landed on may touch the ground, and its first contact must be the other foot alone, on the runway. (3) The jump is the next flight: until it starts only the foot the step landed on may touch the ground, and its first contact must be with the sand (any part of your body). Between the landing of the hop or of the step and the next flight the landing foot stays where it came down: it fails to touch the ground with its centre more than 0.3 m from where it was at the landing (no sliding along and no travelling in hops shorter than a flight). On the runway means: every point of that contact within the runway's width and before the pit. The mark is the point nearest the take-off line at which any part of you touches the sand in the first 2.0 s after the jump's first contact; in that time you may not touch the ground outside the pit nearer the take-off line than the mark. You succeed when that time has passed after a valid hop, step and jump: the mark is then at least 7.0 m. A fall is not a failure by itself. You fail on any of the faults above, if you leave the venue (the level ground ends 8 m to each side of the runway's axis, 45 m behind the take-off line and 6 m beyond the pit) or after 60 s (the time allowed for a trial). No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 2 |
| Memory | 5 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only; the sim sidecar steps and renders on one or two cores (under 1 GB), the agent's container holds the harness and the client
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: author estimate: no trials yet; the agent's container 8 GiB under its 10 GiB cap; whole trial: + the sim service's 8 GiB cap; disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | track-and-jumps |
| Rule book | World Athletics Competition and Technical Rules, 2024 edition: TR 31 (31.1 the hop, step and jump in that order; 31.2 the hop lands on the take-off foot, the step on the other foot; the rules of the long jump apply: TR 29 the runway, the board, the landing area; TR 30.1.1, 30.1.2, 30.1.5 failures; TR 30.3 the measurement), TR 25.17 (one minute for a trial); deviations: TR 31.3 (the take-off line at least 13 m from the pit for men, 11 m for women in international competition; nearer boards for other levels): the board is 7.0 m before the pit, a school competition's board (FAMILIES.md) · TR 31.2, note (a touch of the ground by the 'sleeping' leg is no failure): not applied: between the hop's landing and the step's take-off, and between the step's landing and the jump's take-off, only the foot the phase landed on may touch the ground; a referee without eyes cannot tell a scrape from a supporting step · TR 31.1 (the event is one hop, one step and one jump): between a phase's landing and the next take-off the landing foot is on one place: a touch of it more than 0.3 m from where it landed is a failure (hops too short to be flights, or a slide, would otherwise cover the distance) · the take-off of the hop from one foot (implied by TR 31.2) is judged by a number: the other foot must have left the ground at least 0.05 s before the take-off foot does · TR 30.1.3 (somersaulting) and TR 30.1.6 / 30.2 (how the athlete leaves the landing area) are not judged; the landing is judged for 2.0 s from the first contact with the sand · TR 29.3 (the plasticine indicator board): no imprint; the take-off line is judged geometrically: a foot on the ground with any part of it (also a part in the air) on or over the line's plane is a failure · TR 29.6 (the sand): the pit is a box with a soft, overdamped, high-friction contact (time constant 0.05 s, full stiffness only 0.04 m deep, friction 1.5); it keeps no imprint, so the mark is the contact with the sand nearest the take-off line · TR 31 does not define a hop; here each phase is a flight of at least 0.05 s, and the hop must raise the pelvis at least 0.05 m above its height at lift-off; no wind; one trial |
| Stages | hop → step → jump → landing |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
