# robofunolympics-juggle-three-i00-standard

| | |
|---|---|
| Benchmark | RoboFunOlympics |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robofunolympics-juggle-three-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggle_three` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/robofunolympics/tests/test_juggle_three.py: positive by injection (the hands still, real grip releases and catches, each released ball put on an arc to the other palm); negatives: a ball coming down on its own hand, gripped by its own hand, a low pass, out of order, the waiting ball pushed, onto the head. With still hands the outgoing ball always meets the incoming one: a cascade needs hands that move; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Juggle three balls in a cascade: throw each ball from one hand in an arc to the other, the hands in turn, until 10 catches have been made in a row. (RoboFunOlympics `juggle-three`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Each throw has to land on a palm a few centimetres wide 0.4 m away, about 0.6 s later, and the catching hand must have thrown its own ball before: three balls, two hands, never two in one. Errors add up from throw to throw, because a ball is thrown from wherever it was caught. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `robofunolympics-juggle-three-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, then the service replays the recorded attempt in a fresh simulator;
`tests/grade.py` reads `/data/final.json`: pass iff the live run and the replay succeed and end in the same state. The
rules: Three balls (0.07 m across, 0.13 kg). At the start your forearms are level, the palms up; the blue ball is gripped on your left palm, the yellow ball on your right palm, and the red ball waits 0.14 m above your right palm: it stands for the second ball of the right hand and is thrown for you at t = 2.0 s, on an arc that rises 0.5 m and comes down on where your left palm is at the start. Before that it may not be touched (by you or by a ball you hold). A hand grips one ball at a time: its grip closes on a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it. A throw: a hand lets go of its ball and the ball, touching nothing but air, rises at least 0.3 m above the point where it was let go; only the rise before the ball first touches you again counts. A catch: a hand grips a ball that has been thrown by the other hand (the red ball's first throw counts as the right hand's), at the latest 0.15 s after the ball first touched you again. The cascade's order: the catches alternate between the hands, the left hand first, and take the balls in the order red, blue, yellow, red, ... You succeed at the 10th catch. You fail if a ball touches the ground; if a ball in flight touches any part of you other than a hand, or still touches the hand that threw it later than 0.1 s after the release; if a ball is gripped by the hand that let go of it, or before it has risen 0.3 m; if a ball that has touched a hand again is not gripped within 0.15 s (it rests on the hand or bounces off it); if a catch is out of the cascade's order (the wrong hand or the wrong ball); if the waiting ball is touched before its launch; if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than your feet on the ground); or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | throwing-catching-striking |
| Rule book | No rule book: the three-ball cascade as jugglers define and count it (siteswap 3; the International Jugglers' Association counts a run in catches): each ball is thrown from one hand and caught by the other, the hands throw in turn, the balls follow one another in a fixed order; a run ends with a drop; deviations: A hand holds one ball at a time by a grip switched on and off (it closes on a ball whose surface is within 3.5 cm of the palm and that moves no faster than 6 m/s relative to it), so "two balls in one hand at the start" is modelled: the first of the two (the red ball) waits 0.14 m above the right palm and is thrown by the venue at t = 2.0 s, on an arc that rises 0.5 m and comes down on where the left palm is at the start. Until then it may not be touched. · A throw is a release after which the ball, touching nothing, rises at least 0.3 m above where it was let go; a hand-to-hand pass is not a throw. So that a ball laid on the other hand and lifted is not one, the rise counts only until the ball first touches you again, and from that first touch the other hand has 0.15 s to grip it. · The balls are spheres of a juggling ball's size and mass with a soft bounce; they fly in air (MuJoCo's ellipsoid fluid model: drag, a quasi-steady model), still air. |
| Stages | first catch → half way → ten catches |
| Service | `environment/sim/server.py` (the RoboFunOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/robofunolympics.md) |
