# tennis-match-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tennis_match` |
| Oracle | `full` — solution/: a scripted camera-only player; checked valid at L1-L4 and x1-x20 |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A simulated Franka Panda arm on an x-y rail base, holding a tennis racket, plays a singles match (first to 5
points, from 4:4 by 2, at most 7; the opponent serves every point; the same rules as the duel) against a scripted computer opponent on a regulation court, in real time
slowed by a factor S. The ball has drag, Magnus lift and hard-court bounce and racket impact laws. The agent sees the
ball only through two cameras and may write a player program that observes and acts on its own; it may fix and
restart the program at any time and reviews after every point. The prompt follows the general program-play structure
(`scripts/olympiad/program_prompt.py`) with tennis' sections (`scripts/olympiad/tennis/tennis_prompt.py`).

## Difficulty
Set at run time: opponent level 1-4 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 424, 434]}, slowdowns [1, 2, 5, 10, 20]. An act takes effect
ceil(0.5 s / (0.01 S s)) control steps after it is accepted (50 at x1, 5 at x10), so small S leave little time.

## Reference solution
`solution/solve.sh` runs a scripted player that uses only the camera images, the robot state in the replies
and the documented geometry and physics (`solution/oracle_play.py`, `solution/tn_player.py`: ball detection, a
least-squares flight fit through the bounce, contact choice, the racket face from the contact law).

## Verification
The `sim` service records the match; a fresh process replays it from the logged commands (recomputing every
stroke plan) and must reproduce the score, the final state hash and every joint target. A separate verifier
(`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic replay; no
simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `slowdown`, `official_config`,
`valid_trial` and `technical_failure`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Run | `scripts/olympiad/run_single.sh --task tennis-match-wallclock-program-standard --agent opus\|astra\|oracle\|nop --level L --slowdown S --seed N` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Format | The duel's rules, format and limits: first to 5 points, from 4:4 a lead of 2, at 6:6 the next point wins (at most 7); volleys except on the serve; net cord; a serve that misses the box or touches the net is replayed with a new serve from the same half; the match also ends after 400 racket hits (both players) or 40 points played, the player ahead winning, at equal points the winner of the last point (no draws; `match_limit` in `reward.json`). The scripted opponent serves every point (`match.first_player` = opponent; the agent always receives), the box changing every two points (deuce, deuce, ad, ad, ...) as in the duel |
| Rules | ITF Rules of Tennis 2026 (English), https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf. Deviations: one tie-break-style game to 5 points instead of games and sets (Rules 5-7): from 4:4 a lead of 2 is needed, at most 7 points (tie-break-like, Rule 5 b); the serve is a machine-like serve the player only receives, and a serve that misses the box or touches the net is replayed (no service faults, Rules 19-22); only the strings touch the ball, it passes through the frame, arm and base (Rule 24 i); the robot moves on rails over the back part of its half. Aligned: volleys are legal except on the serve (Rule 24 e), the serve must land in the service box diagonally opposite (Rule 17) else it is replayed, a rally ball that touches the net's top edge and lands in the correct court is good (net cord, Rule 25 a) while a serve touching the net is a let (Rule 22 a), lines are in (Rule 12) |
| Origin | `tennis-match-l{1..4}-wallclock-x10-interactive[-seed2\|-seed3]` (dev/chi): same court, ball, robot, stroke controller, opponent and replay; program-play act rule, one act in flight, the camera-only reference instead of the privileged one (its `/oracle/state` endpoint is removed) |
| Generator | `scripts/olympiad/generate.py` |
