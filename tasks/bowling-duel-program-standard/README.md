# bowling-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (ball release primitive)` |
| Family / instance | `bowling_duel` |
| Oracle | `full` — solution/: the reference player (precomputed releases per official seed) on either seat; oracle against oracle plays valid matches with both first players |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents each bowl a 10-frame game of ten-pin bowling on their own MuJoCo lane. The lanes are identical and so
is the release scatter (seeded by seed, frame and ball), so the same release gives the same result on both lanes.
Frames alternate: a player bowls a whole frame (a review after each ball), then the other; the first player leads
every frame. An action out of turn is refused (HTTP 409); `game wait` returns when it is the player's turn. Each
player has a 60-minute chess clock (its turns only, reviews included; clock out = loss). The higher total wins; equal
totals go to a roll-off (USBC 118b: one frame scored like a 10th, repeated while level, at most 3), then the player
with more chess-clock time left wins: there are no draws. A player sees only its own lane and hears the opponent's pin
counts. Single and duel play by the same rules (frames, scoring, gutter and pin rules, limits).

## Difficulty
Set at run time: the seed (`DUEL_SEED`; official [20260930, 2, 3]) and the first player (`FIRST_PLAYER`, A or B).
Play both orders for a fair comparison.

## Reference solution
`solution/` holds the reference player (precomputed releases per official seed), usable on either seat. The two
seats' references differ slightly so that two references do not tie: seat B lays every ball down half a board further
left than seat A (on the official seeds A bowls 300, B 244 / 247 / 160).

## Verification
The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay of both games; `success` = 1 iff the match is valid and decided (played out, or won on the opponent's clock or
start); the winner is `A_won` / `B_won` (exactly one in a valid match). `reward.json` also reports both totals, the
roll-off frames (`tiebreaks`), whether the clock decided (`clock_decided`), `official_config`, `technical_failure`,
`clock_forfeit` and `start_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | USBC Playing Rules 2025-2026 (Chapter 2, General Playing Rules; rev. 07/25), https://bowl.com/getmedia/cabf49db-8cc5-4ce4-abc0-dfca1a1d7706/071724_USBC-Playing-Rules.pdf; a tie goes to a roll-off (USBC 118b), at most 3 frames, then more chess-clock time left wins |
| Deviations | pin down = tilted more than 20 degrees or off the lane surface (approximates USBC 6a); no fouls (the release starts past the foul line, USBC 5a); no rear cushion (open pit, USBC 6b.2); the roll-off stops after 3 frames (USBC 118b continues until the tie is broken) |
| Parameters | `DUEL_SEED` (default 20260930), `FIRST_PLAYER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task bowling-duel-program-standard --a opus\|astra\|oracle --b ... [--seed N] [--first A\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / clock | 30 minutes to start after the first player; one 60-minute chess clock per player |
| Generator | `scripts/olympiad/generate.py` |
