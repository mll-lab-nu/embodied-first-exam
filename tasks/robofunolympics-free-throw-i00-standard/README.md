# robofunolympics-free-throw-i00-standard

| | |
|---|---|
| Benchmark | RoboFunOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robofunolympics-free-throw-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `free_throw` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/robofunolympics/tests/test_free_throw.py: positive by injection (a real underhand swing and release at 7.4 m/s, the ball's velocity set to 8.1 m/s at 58 degrees: a real flight and ring); negatives: not released in 5 s, the floor, touched again, the line, the semi-circle, from below, a fall. The shot needs 8.06 m/s at 58 degrees; the arm reaches 11 m/s with the elbow fired late, and about 400 search evaluations came within 0.37 m of the ring's centre; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Shoot a free throw: from behind the free-throw line, throw the basketball in your right hand so that it enters the basket from above. (RoboFunOlympics `free-throw`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
From a hand about a metre above the floor the 0.62 kg ball needs to leave at about 8 m/s on a steep arc to reach a ring 3.05 m high and more than 4 m away, with a margin of a few centimetres in air that slows it, and within five seconds. A straight-arm swing at the shoulder's speed limit gives less than that, and the body only stands by an open-loop stance. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `robofunolympics-free-throw-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). It starts gripped in your right hand and is at your disposal at the start. The free-throw line's edge nearest to you is 4.225 m from the point under the ring's centre; the free-throw semi-circle has a radius of 1.8 m round the middle of that edge. You succeed when, after you have let go of the ball, its centre goes down through the ring's plane inside the ring and on down to one ball diameter below it. You fail if you have not let go of the ball within 5.0 s; if, before the ball has touched the ring or entered the basket, any part of you touches the floor on or beyond the free-throw line's near edge or outside the semi-circle; if any part of you touches the ball more than 0.05 s after you let go of it (it cannot be gripped again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 12 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 16 (goal), Art. 43 (free throws); deviations: Art. 3 (equipment): the hand holds the ball by a grip switched on and off, not by fingers; the ball is released when the grip is switched off. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and no rebound: one throw, and touching the ball after the release ends the attempt. |
| Stages | release → through the ring |
| Service | `environment/sim/server.py` (the RoboFunOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1200 control steps (12 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/robofunolympics.md) |
