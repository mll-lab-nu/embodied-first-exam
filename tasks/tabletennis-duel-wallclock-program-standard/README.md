# tabletennis-duel-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_duel` |
| Oracle | `full` — solution/: two scripted camera-only players play valid matches (checked at x10 and x20) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents each control a simulated Franka Panda arm with a table-tennis paddle and play a match (first to 5
points; from 4:4 a lead of 2 is needed, at 6:6 the next point wins) in a shared world running in real time, slowed by a
factor S; a neutral machine serves and the receiver changes every point. Each may write a player program that observes
and acts on its own, fix it at any time and review after every point (300 s, else forfeit).

## Difficulty
Set at run time: slowdown S (`RCB_SLOWDOWN`; official [10, 20]), seed (`DUEL_SEED`) and first receiver
(`FIRST_RECEIVER`). Play both seat orders for a fair comparison.

## Reference solution
`solution/` holds the scripted reference player; with both seats `oracle` the match is valid.

## Verification
The `sim` service records the match and the verifier (`tests/grade.py`, no network) replays it; `success` = 1
iff the match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json` also
reports both seats' points, `official_config`, `technical_failure` and `ready_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B) |
| Rules | ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2, effective 1 January 2025): https://db.ittf.com/sites/default/files/public/2025-02/ITTF_Statutes_2025_tracked_changes_version.pdf. The same rules as the single-player task: a return may touch the net (2.7.1); a serve that touches the net is a let (2.9.1.1; the recorded serves clear the net by >= 3.9 cm); a shot that passes a player's half and then hits that player's robot is out, contact over or towards a robot's half is obstruction (2.10.1.4, 2.10.1.6); the expedite rule applies from the first point: the receiver's 13th good return in a rally wins it the point (2.15.4), which bounds every rally; the match always has a winner: the format caps it at 7 points, and at the guard of 40 points (lets included, never reached in practice) the player ahead wins, at a level score the player who won the last point. Deviations: one game to 5 points, lead by 2 from 4:4, at 6:6 the next point wins (instead of best-of games to 11, 2.11, 2.12); a neutral machine serves recorded real serves, the receiver changes every point (2.6, 2.13.3, 2.15.3); only the blade can strike, the ball touching the handle or arm loses (2.5.7); no free hand: any arm or paddle contact with the table, net or floor loses (2.10.1.9-11); any double hit loses, deliberate or not (2.10.1.7) |
| Run | `scripts/olympiad/run_duel.sh --a opus\|astra\|oracle --b ... --slowdown S [--seed N] [--first A\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |
