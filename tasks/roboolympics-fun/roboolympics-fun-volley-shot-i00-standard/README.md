# roboolympics-fun-volley-shot-i00-standard

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `roboolympics-fun-volley-shot-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `volley_shot` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_volley_shot.py: positive by injection (the real cross onto the foot, the ball's velocity set at the contact: in at 11.7, out at 18.4 m/s, into the goal); negatives: a still leg (the ball leaves slower than it came), a body contact, carried, wide, at the keeper, a second touch, too close, in without a volley; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Volley the cross: strike the football that is crossed to you from the wing with a foot before it touches the ground, into the official goal 11 m away, past the goalkeeper dummy. (RoboOlympics `volley-shot`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball crosses the reach of a leg in a few hundredths of a second, at 11 m/s and at right angles to the goal: the foot has to meet it in the air with a swing of its own, fast enough that the ball leaves faster than it came, aimed 11 m into the goal and beside the dummy, by a 67 kg robot on one leg whose walking policy has no kick. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 50 resets (only the last attempt is graded).

## Reference solution
None (as `roboolympics-fun-volley-shot-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17, board 0151); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand on the penalty mark, facing the goal; the goal line is 11.0 m ahead of you. The goal is 7.32 m wide between the posts and 2.44 m high under the crossbar (posts and bar 0.12 m thick), centred on the line you face along. A goalkeeper dummy, a board 1.9 m high, 0.6 m wide and 0.3 m thick, stands still on the goal line at the centre of the goal. A size-5 football (0.22 m across, 0.43 kg, in air) waits on the ground on the left wing, 20.0 m from you, and 3.0 s after the start it is crossed: a lofted ball with backspin that comes down in front of you. The volley is the ball's first contact after the cross: with a foot or an ankle of yours (the parts below the shin), before the ball has touched the ground. Every contact within 0.15 s of the first belongs to the one strike, which is over when the ball has been clear of you for 0.03 s; and it must be a strike: the ball's speed when it leaves your foot is at least 1.0 times its speed just before the foot touched it. You succeed at the moment the whole ball is then over the goal line between the posts and under the bar; after the strike it may touch the ground, the posts, the bar and the dummy. You fail if the ball touches the ground before your strike, if any part of you other than a foot or an ankle touches the ball at any time, if the strike's contacts last longer than 0.15 s, if the ball leaves the foot slower than that, if you touch the ball again after the strike, if the whole ball crosses the goal line outside the goal, if after the strike the ball has been slower than 0.1 m/s for 1.0 s, if your pelvis comes within 9.15 m of the waiting ball before it is crossed, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground), or after 10 s. The waiting ball cannot be touched. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | football-and-volleyball |
| Rule book | IFAB Laws of the Game 2025/26: Law 1 (the goal 7.32 m x 2.44 m with posts and crossbar 12 cm wide, the penalty mark 11 m from the goal line, the penalty area, the goal area), Law 2 (a size-5 ball: 68-70 cm round, 410-450 g), Law 10 (a goal: the whole ball over the goal line between the posts and under the bar), Law 12 (handball), Law 13 (9.15 m from the ball until it is in play) and the glossary (a kick is a contact with the foot or the ankle); deviations: The cross is a scripted launch: a fixed lofted kick with backspin from a point 20.0 m away on the left wing, the same in every attempt, instead of a team-mate. · The goalkeeper is a dummy, a rigid board 1.9 m high and 0.6 m wide that stands still on the goal line at the centre of the goal: an opponent cannot be simulated. · A volley is judged by numbers instead of a referee's eye: every contact within 0.15 s of the first is the one strike, and a strike is a ball that leaves the foot at least 1.0 times as fast as it arrived (a ball that only rebounds from a leg held in its path leaves slower: it is not a shot). · Law 13's distance is applied to the robot itself: until the cross is played it stays 9.15 m from the ball, so that the cross is played, not met at the kicker. · The Laws allow any number of touches and any part but the arms; the task is narrower than the Laws: one touch, with a foot or an ankle only, before the cross touches the ground (the task is a volley, not open play). · Law 1: only the goal end of the field is there; the goal's net is a rigid cage 2.0 m deep; no wind, no other player. |
| Stages | volley → goal |
| Service | `environment/sim/server.py` (the RoboOlympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 50 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
