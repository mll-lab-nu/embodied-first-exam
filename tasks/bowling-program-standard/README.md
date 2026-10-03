# bowling-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (ball release primitive)` |
| Family / instance | `bowling` |
| Oracle | `full` — solution/: the privileged reference player's precomputed releases for each official seed (300 on 20260930, 2 and 3), played through the service's HTTP calls; other seeds: a fixed release |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A 10-frame game of ten-pin bowling on a regulation MuJoCo lane (oiled front end, dry back end; 10 rigid pins,
a 7 kg ball). The agent sees the lane only through cameras and rolls each ball with a release (board, launch angle,
speed, rev rate, axis rotation; seeded scatter). It may write a program that observes and bowls on its own, fix it at
any time and reviews after every ball. A 60-minute chess clock runs on the agent's turns (simulation excluded). Success:
a total of 200 or more. The prompt follows the turn-based program-play structure
(`scripts/olympiad/turn_prompt.py`) with bowling's sections (`scripts/olympiad/bowling/bowling_prompt.py`).

## Difficulty
Set at run time: the seed (`RCB_SEED`: the lane's oil pattern and friction, and the release scatter). Official
seeds: [20260930, 2, 3] (the old `bowling-interactive[-seed2/3]`). One game varies a lot (the same bowler's games spread
by about 25-30 pins); the score is always reported.

## Reference solution
`solution/solve.sh` runs the reference player (`solution/oracle_play.py`): the releases the privileged reference
player computed offline for each official seed (true pin poses and the real lane; grid search and Monte Carlo over
the scatter), sent through the same HTTP calls a player program uses.

## Verification
The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the fresh-process
replay (`replay_check.json`: every recorded release reproduces the state and the score) and writes `success` = 1 iff
the game is valid, played out (no clock out) and scores at least 200. `reward.json` also reports `total`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, the clock used and the per-frame pins. A gutter ball scores no
pins (USBC 6b.1) and a pin standing anywhere on the lane counts as standing (USBC 7b).
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | USBC Playing Rules 2025-2026 (Chapter 2, General Playing Rules; rev. 07/25), https://bowl.com/getmedia/cabf49db-8cc5-4ce4-abc0-dfca1a1d7706/071724_USBC-Playing-Rules.pdf |
| Deviations | pin down = tilted more than 20 degrees or off the lane surface (approximates USBC 6a); no fouls (the release starts past the foul line, USBC 5a); no rear cushion (open pit, USBC 6b.2) |
| Parameters | `RCB_SEED` (default 20260930) |
| Run | `scripts/olympiad/run_single.sh --task bowling-program-standard --agent opus\|astra\|oracle\|nop --level 1 --seed N` |
| Time | a 60-minute chess clock, running from `game start` on the agent's turns, reviews included, simulation excluded; clock out = loss |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
