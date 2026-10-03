# curling-match-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `curling-fcv1 (MuJoCo renderer)` / `none (stones)` |
| Family / instance | `curling_match` |
| Oracle | `full` — solution/: a scripted camera-only player; checked valid at L1-L2 on official seeds, it can win or lose (checked: valid at L1 and L2) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Curling against a scripted computer team: the agent skips the yellow team and throws every yellow stone (4 ends
of 5 stones per team, up to 3 extra ends while tied, then the player with more chess-clock time left wins; the opponent
has the hammer in end 1 and its clock never runs; the free guard
zone five-rock rule; DigitalCurling's FCV1 ice model with impulse collisions). It sees the
sheet only through a top-down house camera and an end camera (no stone coordinates) and throws by release speed,
angle and spin. Turn-based: a 60-minute chess clock runs only on the agent's turn (reviews included; clock out =
loss), and the agent reviews each of its throws. It may write a program that measures the images and sends its
throws. The prompt follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`) with
curling's sections (`scripts/olympiad/curling/curling_prompt.py`).

## Difficulty
Set at run time: opponent level 1-2 (`RCB_LEVEL`; level 2 throws about as precisely as the agent and also
plays off-centre and firm takeouts and guards) and the seed of the execution noise (`RCB_SEED`). Official
configurations: levels with seeds {1: [7101, 7111, 7121], 2: [7202, 7212, 7222]} (from the original `curling-match[-l2]-interactive` tasks).

## Reference solution
`solution/solve.sh` runs a scripted player that uses only the house camera image and the documented ice model
(`solution/curling_player.py`: stones from the grey granite bodies in the image, back-projected to the sheet; takeouts
of the opponent's shot stone and draws to free spots near the button, aimed with the documented ice law and checked
for a clear path; no takeouts through guards while the free guard zone rule is in force).

## Verification
The `sim` service records the match; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent wins a valid match (deterministic replay; no simulator,
model-API or metering failure; the clock did not run out). `reward.json` also reports `level`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, `points_for` / `points_against`, `clock_tiebreak` and `clock_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SEED` (default: the level's first official seed, 7101 or 7202) |
| Rules | World Curling, The Rules of Curling and Rules of Competition, July 2025 (https://worldcurling.org/wp-content/uploads/2025/08/Rules-2025.pdf). Deviations: 4 ends of 5 stones per team (C5, R2(b): 8 or 10 ends of 8 stones); at most 3 extra ends, then the player with more chess-clock time left wins (R12(a): extra ends until a team scores); no sweeping (R8); the stone is released at the hack with the given speed, direction and spin (no delivery rules, R5); no no-tick rule (R7); single player: the opponent has the hammer in end 1 (a fixed handicap; R5(a): coin toss or last stone draw) |
| Run | `scripts/olympiad/run_single.sh --task curling-match-program-standard --agent opus\|astra\|oracle\|nop --level L --seed N` |
| Time | chess clock: 60 minutes (`clock.total_s` in `/spec`), only on the agent's turn; review after each of its throws |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
