# curling-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `curling-fcv1 (MuJoCo renderer)` / `none (stones)` |
| Family / instance | `curling_duel` |
| Oracle | `full` — solution/: the scripted camera-only player on either seat; oracle against oracle plays valid matches (both FIRST_PLAYER orders) |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents play the curling match rules (4 ends of 5 stones per team, up to 3 extra ends while tied, the free guard
zone rule, the FCV1 ice model)
against each other, seat A with the yellow stones and seat B with the red ones, each from its own container through the
same cameras and throw interface. The stones alternate as the rules say (the team without the hammer throws first);
an action out of turn is refused (HTTP 409). Each has its own 60-minute chess clock that runs only on its turn
(reviews included; clock out = loss) and reviews each of its throws.

## Difficulty
Set at run time: `DUEL_SEED` (the execution noise) and `FIRST_PLAYER` (A or B: throws the first stone of end
1, so the other player has the hammer in end 1). Official configurations: seeds [1, 2, 3], each with both values of
`FIRST_PLAYER`, so each pairing plays both orders.

## Reference solution
`solution/` holds the scripted camera-only reference player (either seat); with both seats `oracle` the match is valid.

## Verification
The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the
fresh-process replay; `success` = `valid_trial` = 1 iff the match is complete (played out, or decided by a clock or start
forfeit), deterministic, and free of metering or model-API failures. The winner is `A_won` / `B_won` (they sum to 1; there is no
draw: a tie after the last extra end goes to the player with more chess-clock time left, `clock_tiebreak`);
`reward.json` also reports `A_points` / `B_points`, `seed`, `first_player` (0 = A),
`official_config`, `clock_forfeit` and `start_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task curling-duel-program-standard --a opus\|astra\|oracle --b ... --seed N --first A\|B` |
| Format | the single-player match rules: 4 ends x 5 stones per team, up to 3 extra ends while tied, then the player with more chess-clock time left wins; A yellow, B red; `FIRST_PLAYER` throws first in end 1 (the other has the hammer); after an end the scorer throws first, a blank end keeps the hammer; the n-th stone of each team in an end gets the same execution error |
| Rules | World Curling, The Rules of Curling and Rules of Competition, July 2025 (https://worldcurling.org/wp-content/uploads/2025/08/Rules-2025.pdf). Deviations: 4 ends of 5 stones per team (C5, R2(b): 8 or 10 ends of 8 stones); at most 3 extra ends, then the player with more chess-clock time left wins (R12(a): extra ends until a team scores); no sweeping (R8); the stone is released at the hack with the given speed, direction and spin (no delivery rules, R5); no no-tick rule (R7) |
| Time | one 60-minute chess clock per player, running only on its turn; review after each of its throws |
| Start | 30 minutes to start after the first player, else forfeit |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |
