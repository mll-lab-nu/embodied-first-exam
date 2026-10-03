# billiards-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `pooltool` / `none (cue)` |
| Family / instance | `billiards_duel` |
| Oracle | `full` — solution/: the scripted camera-only 8-ball player on either seat; oracle against oracle plays valid games (FIRST_PLAYER A and B) |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad-billiards:0.1.0` |

## Task
Two agents play one rack of American 8-ball against each other at one table (the single-player game's rules,
`environment/sim/eightball.py`), each from its own container through the same cameras and shot interface (cue
direction, speed, tip offset; cue placement with ball in hand; the call of every shot after the break). They take
turns as the rules say (a legal shot that pockets the called ball in the called pocket keeps the turn); an action out of
turn is refused (HTTP 409). Each
has its own 60-minute chess clock that runs only on its turn (reviews included; clock out = loss) and reviews each of
its shots.

## Difficulty
Set at run time: `DUEL_SEED` (the rack order and jitter, the execution scatter) and `FIRST_PLAYER` (A or B: who
breaks). Official configurations: seeds [1, 3, 4], each with both values of `FIRST_PLAYER`, so each pairing plays
both orders.

## Reference solution
`solution/` holds the scripted camera-only reference player (either seat); with both seats `oracle` the game is valid.

## Verification
The `sim` service records the game and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay; `success` = `valid_trial` = 1 iff the game is complete (played out, or decided by a clock or start forfeit),
deterministic, and free of metering or model-API failures. The winner is `A_won` / `B_won` (they sum to 1: a tie at the shot limit goes to the player
with more chess-clock time left, `clock_tiebreak`); `reward.json` also reports `A_balls_left` / `B_balls_left` (balls left in the player's group, 7 while
open), `seed`, `first_player` (0 = A), `official_config`, `clock_forfeit` and `start_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A: the breaker) |
| Run | `scripts/olympiad/run_duel.sh --task billiards-duel-program-standard --a opus\|astra\|oracle --b ... --seed N --first A\|B` |
| Format | one rack of 8-ball, the single-player rules; `FIRST_PLAYER` breaks (after an illegal break the other player re-racks and breaks); 60 shots each at most (then fewer balls left in the group wins, an open table counting as 7; if level, more chess-clock time left wins) |
| Rules | WPA Rules of Play, effective 2025-09-15 (https://wpapool.com/wp-content/uploads/2025/09/2025.09.15-WPA-Rules.pdf), section 4 8-Ball, with the fouls of section 3. Deviations: the 8 pocketed on the break is always spotted (4.3(e)/(f): no re-break option); after an illegal break the other player always re-racks the same rack and breaks (4.3(d)(2) chosen, no other option); a foul on the break gives ball in hand above the head string (4.3(g)/(h)(2) chosen); no spot request with ball in hand above the head string (1.6); every call is explicit, no "obvious" shots (1.7, 4.6); no cue elevation, so no jump or massé shots (2.9); the cue ball cannot be placed touching a ball or in a pocket opening (1.6); a 60-shot limit per player (then fewer balls left, then more chess-clock time left) replaces the stalemate rule (4.11); push out is a 9-Ball rule and does not apply |
| Time | one 60-minute chess clock per player, running only on its turn; review after each of its shots |
| Start | 30 minutes to start after the first player, else forfeit |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Simulator image | `images/olympiad-billiards/` (pooltool 0.6.0, numba; built locally) |
| Generator | `scripts/olympiad/generate.py` |
