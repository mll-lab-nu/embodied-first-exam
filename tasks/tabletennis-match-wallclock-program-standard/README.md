# tabletennis-match-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `tabletennis_match` |
| Oracle | `full` — solution/: a scripted camera-only player; checked valid at L1-L4 and x1-x20, wins L1 (it can lose at L2-L4) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A simulated Franka Panda arm with a table-tennis paddle plays a match (first to 5 points; from 4:4 a lead of 2
is needed, at 6:6 the next point wins: the duel's rules) against a scripted computer opponent, in real time slowed by a factor S. The agent sees the ball only through two cameras and may write a
player program that observes and acts on its own; it may fix and restart the program at any time and reviews after
every point. The prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with table
tennis' sections (`scripts/olympiad/tabletennis/tt_prompt.py`).

## Difficulty
Set at run time: opponent level 1-4 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 414, 424]}, slowdowns [1, 2, 5, 10, 20].

## Reference solution
`solution/solve.sh` runs a scripted player that uses only the camera images and the documented geometry
(`solution/oracle_play.py`).

## Verification
The `sim` service records the match; a separate verifier (`tests/grade.py`, no network) replays it and writes
`success` = 1 iff the agent wins a valid match (deterministic replay; no simulator, model-API or metering failure).
`reward.json` also reports `level`, `seed`, `slowdown`, `official_config`, `valid_trial` and `technical_failure`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Rules | ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2, effective 1 January 2025): https://db.ittf.com/sites/default/files/public/2025-02/ITTF_Statutes_2025_tracked_changes_version.pdf. The same rules as the duel (only the opponent and the serve differ): a return may touch the net (2.7.1); a serve that touches the net is a let (2.9.1.1; the recorded serves clear the net by >= 3.9 cm); a shot that passes a player's half and then hits that player's robot is out, contact over or towards a robot's half is obstruction (2.10.1.4, 2.10.1.6); the expedite rule applies from the first point: the receiver's 13th good return in a rally wins it the point (2.15.4), which bounds every rally; the match always has a winner: the format caps it at 7 points, and at the guard of 40 points (lets included, never reached in practice) the player ahead wins, at a level score the player who won the last point. Deviations: one game to 5 points, lead by 2 from 4:4, at 6:6 the next point wins (instead of best-of games to 11, 2.11, 2.12); the opponent serves every point with recorded real serves and the agent always receives (the robot cannot toss the ball, 2.6; service cannot alternate, 2.13); only the blade can strike, the ball touching the handle or arm loses (2.5.7); no free hand: any arm or paddle contact with the table, net or floor loses (2.10.1.9-11); any double hit loses, deliberate or not (2.10.1.7) |
| Run | `scripts/olympiad/run_single.sh --agent opus\|astra\|oracle\|nop --level L --slowdown S [--seed N]` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
