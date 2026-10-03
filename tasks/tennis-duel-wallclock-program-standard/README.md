# tennis-duel-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tennis_duel` |
| Oracle | `full` — solution/: the camera-only reference player in both seats plays valid matches (checked at x10 and x20, both first receivers) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents each control a simulated Franka Panda arm on an x-y rail base, holding a tennis racket, and play a
singles match (first to 5 points) on a regulation court in a shared world running in real time, slowed by a factor S.
Each may write a player program that observes and acts on its own, fix it at any time and review after every point
(300 s, else forfeit).

## Difficulty
Set at run time: slowdown S (`RCB_SLOWDOWN`; official [10, 20]), seed (`DUEL_SEED`: the machine's
serves and both seats' execution scatter) and the first receiver (`FIRST_RECEIVER`). Play both seat orders for a fair
comparison.

## Reference solution
`solution/` holds the single-player task's camera-only reference player (`tn_player.py`), which plays from
either seat in its own frame (`SEAT`); with both seats `oracle` the match is valid.

## Verification
The `sim` service records both robots' joint targets; a fresh process re-runs the match from them and must
reproduce the score, the points and the final state hash. The verifier (`tests/grade.py`, no network) writes `success`
= 1 iff the match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json`
also reports both seats' points (`A_points`, `B_points`), `official_config`, `technical_failure` and `ready_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task tennis-duel-wallclock-program-standard --a opus\|astra\|oracle --b ... --slowdown S [--seed N] [--first A\|B]` |
| Format | Mirrored court: each player sees and acts in its own frame (its half y < 0, home (0, -11.4)), with the single-player cameras and stroke interface. A neutral serving machine (the single-player level-1 serve generator, seeded by `DUEL_SEED` and the points played) serves from behind the non-receiver's base line. The receiver changes every point (`FIRST_RECEIVER` = `match.first_player` receives points 1, 3, 5, ...); the box changes every two points (deuce, deuce, ad, ad, ...). First to 5 points; from 4:4 a lead of 2 is needed, at 6:6 the next point wins (at most 7). The serving-side robot cannot touch the serve; a serve out of the box or into the net is a let, replayed from the same half with a new serve. The match also ends after 400 racket hits or 40 points played (lets included): the player ahead wins, at equal points the winner of the last point (no draws; `match_limit` in `reward.json`, a result, not a technical failure). The rules, format and limits are those of the single-player game; only the opponent, the machine serve and the receiver rotation differ. Play both seat orders |
| Rules | ITF Rules of Tennis 2026 (English), https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf. Deviations: one tie-break-style game to 5 points instead of games and sets (Rules 5-7): from 4:4 a lead of 2 is needed, at most 7 points (tie-break-like, Rule 5 b); the receiver changes every point; the serve is a machine-like serve the player only receives, and a serve that misses the box or touches the net is replayed (no service faults, Rules 19-22); only the strings touch the ball, it passes through the frame, arm and base (Rule 24 i); the robot moves on rails over the back part of its half. Aligned: volleys are legal except on the serve (Rule 24 e), the serve must land in the service box diagonally opposite (Rule 17) else it is replayed, a rally ball that touches the net's top edge and lands in the correct court is good (net cord, Rule 25 a) while a serve touching the net is a let (Rule 22 a), lines are in (Rule 12) |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Scene | `scene_extra/tn_duel.xml` (made by `scripts/olympiad/tennis/mk_duel_scene.py`: robot B mirrors robot A) |
| Generator | `scripts/olympiad/generate.py` |
