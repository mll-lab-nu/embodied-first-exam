# billiards-eightball-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `pooltool` / `none (cue)` |
| Family / instance | `billiards_eightball` |
| Oracle | `full` — solution/: a scripted camera-only 8-ball player; wins the default L1 configuration (seed 1), checked valid at L1 and L2 (it can lose) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad-billiards:0.1.0` |

## Task
One rack of 8-ball against a scripted computer opponent on a simulated 7-ft table (pooltool's event-based physics
with spin, cushions and pockets). The agent sees the table only through an overhead camera and a sighting camera (no
ball coordinates) and shoots by cue direction, cue speed and tip offset; with ball in hand it also places the cue ball,
and every shot after the break is called (ball and pocket, or safety). The rules (`environment/sim/eightball.py`) are
the WPA Rules of Play (effective 2025-09-15) for 8-Ball with the deviations in the Rules row below. A 60-shot limit per
player ends every game (then fewer balls left wins; if level, more chess-clock time left; the scripted opponent's clock
never runs). Turn-based: a
60-minute chess clock runs only on the agent's turn (reviews included; clock out = loss), and the agent reviews each of
its shots. It may write a program that measures the images and sends its shots. The prompt follows the general
turn-based program-play structure (`scripts/olympiad/turn_prompt.py`) with 8-ball's sections
(`scripts/olympiad/billiards/billiards_prompt.py`).

## Difficulty
Set at run time: opponent level 1-2 (`RCB_LEVEL`; level 1: aim error 0.5 deg, the agent breaks; level 2: aim
error 0.25 deg, safer shot selection, the opponent breaks) and the rack seed (`RCB_SEED`: the order of the balls in the
rack, a small rack jitter, the execution scatter). Official configurations: levels with seeds {1: [1, 3, 6], 2: [2, 4, 8]},
chosen so that both players get several turns.

## Reference solution
`solution/solve.sh` runs a scripted player that uses only the top camera image, the documented geometry and the
rules (`solution/eight_player.py`: ball centres from a distance transform of the image, solids / stripes / 8 / cue ball
from their colours; the break from the head spot; ball in hand placed for a straight pot; the easiest direct pot of its
group by ghost-ball geometry, called as ball and pocket (numbers read from the ball colours); a firm hit called
safety when it has no pot).

## Verification
The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent wins a valid game (deterministic replay; no simulator,
model-API or metering failure; the clock did not run out). `reward.json` also reports `level`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, `your_balls_left` / `opponent_balls_left`, `lost`, `clock_tiebreak` and
`clock_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SEED` (default: the level's first official seed, 1 or 2) |
| Run | `scripts/olympiad/run_single.sh --task billiards-eightball-program-standard --agent opus\|astra\|oracle\|nop --level L --seed N` |
| Action | `shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=BALL:POCKET\|safety]` (cue placement only with ball in hand; a call on every shot but the break) |
| Rules | WPA Rules of Play, effective 2025-09-15 (https://wpapool.com/wp-content/uploads/2025/09/2025.09.15-WPA-Rules.pdf), section 4 8-Ball, with the fouls of section 3. Deviations: the 8 pocketed on the break is always spotted (4.3(e)/(f): no re-break option); after an illegal break the other player always re-racks the same rack and breaks (4.3(d)(2) chosen, no other option); a foul on the break gives ball in hand above the head string (4.3(g)/(h)(2) chosen); no spot request with ball in hand above the head string (1.6); every call is explicit, no "obvious" shots (1.7, 4.6); no cue elevation, so no jump or massé shots (2.9); the cue ball cannot be placed touching a ball or in a pocket opening (1.6); a 60-shot limit per player (then fewer balls left, then more chess-clock time left) replaces the stalemate rule (4.11); push out is a 9-Ball rule and does not apply. pooltool's own `ruleset.eight_ball` is not used (it is tied to pooltool's game loop); its event helpers are |
| Time | chess clock: 60 minutes (`clock.total_s` in `/spec`), only on the agent's turn; review after each of its shots |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Simulator image | `images/olympiad-billiards/` (pooltool 0.6.0, numba; built locally) |
| Generator | `scripts/olympiad/generate.py` |
