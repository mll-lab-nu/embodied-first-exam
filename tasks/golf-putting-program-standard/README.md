# golf-putting-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (putter stroke primitive)` |
| Family / instance | `golf_putting` |
| Oracle | `full` — solution/: the privileged reference player's precomputed strokes for each official seed (5, 6 and 5 strokes on 20260928, 13 and 14), played through the service's HTTP calls; other seeds: straight putts |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A 4-hole mini-golf putting round (par 9) on sloped greens with walls and an obstacle block (a deterministic
rolling-ball and cup model; MuJoCo renders the scene). The agent sees the course only through cameras and plays each
stroke with an aim and a speed (seeded scatter). It may write a program that observes and putts on its own, fix it at
any time and reviews after every stroke. A 60-minute chess clock runs on the agent's turns (simulation excluded).
Success: the round in 9 strokes or fewer. The prompt follows the turn-based program-play structure
(`scripts/olympiad/turn_prompt.py`) with golf's sections (`scripts/olympiad/golf/golf_prompt.py`).

## Difficulty
Set at run time: the seed (`RCB_SEED`: where the ball and the cup are, the tilts, bumps and ridges, and the
stroke scatter). Official seeds: [20260928, 13, 14] (the old `golf-putting-interactive[-seed13/14]`).

## Reference solution
`solution/solve.sh` runs the reference player (`solution/oracle_play.py`): the strokes the privileged reference
player computed offline for each official seed (true positions and physics; grid search over aim and speed, the most
robust holed cell), sent through the same HTTP calls a player program uses.

## Verification
The `sim` service records the round; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay (`replay_check.json`: every recorded stroke reproduces the state and the score) and writes
`success` = 1 iff the round is valid, complete (no clock out) and takes at most 9 strokes. `reward.json` also reports
`total`, `to_par`, per-hole scores, `seed`, `official_config`, `valid_trial`, `technical_failure` and the clock used.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | WMF Rulebook 2.3, Worldwide international sport rules (World Minigolf Sport Federation), https://gov.minigolfsport.com/rules/2_3.pdf; secondary: R&A/USGA Rules of Golf 2023, https://www.randa.org/rog; scoring as WMF 9.1 (6 strokes, then 7) |
| Deviations | greens enclosed by walls: no border line, no out of bounds (WMF 2.7, 8); a chess clock instead of the per-stroke time limit (WMF 11.3) |
| Parameters | `RCB_SEED` (default 20260928) |
| Run | `scripts/olympiad/run_single.sh --task golf-putting-program-standard --agent opus\|astra\|oracle\|nop --level 1 --seed N` |
| Time | a 60-minute chess clock, running from `game start` on the agent's turns, reviews included, simulation excluded; clock out = loss (the unfinished holes score 7) |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
