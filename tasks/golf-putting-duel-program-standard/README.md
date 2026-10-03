# golf-putting-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (putter stroke primitive)` |
| Family / instance | `golf_putting_duel` |
| Oracle | `full` — solution/: the reference player (precomputed strokes per official seed) on either seat; oracle against oracle plays valid matches with both first players |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents play the same 4-hole mini-golf putting round, each with its own ball; the balls never meet: a player
plays a hole alone, from the start to the cup (a review after each stroke), then the other plays the same hole.
Whoever plays a hole second plays the next hole first (hole 1: the first player), so each leads two holes. The stroke
scatter is the same for both (seeded by seed, hole and stroke). An action out of turn is refused (HTTP 409); `game wait`
returns when it is the player's turn. Each player has a 60-minute chess clock (its turns only, reviews included; clock
out = loss). Fewest strokes wins; equal totals go to a sudden-death play-off (WMF 9.3: holes 1, 2, ... again, each
scored alone, at most 4), then the player with more chess-clock time left wins: there are no draws. A player sees only
its own ball and hears the opponent's results. Single and duel play by the same rules (holes, scoring, pick-up rule,
limits).

## Difficulty
Set at run time: the seed (`DUEL_SEED`; official [20260928, 13, 14]) and the first player (`FIRST_PLAYER`, A or B).
Play both orders for a fair comparison.

## Reference solution
`solution/` holds the reference player (precomputed strokes per official seed), usable on either seat. The two
seats' references differ slightly so that two references do not tie: seat B aims 0.2 degrees further counter-clockwise
than seat A (on the official seeds A takes 5 / 6 / 5 strokes, B 6 / 22 / 10).

## Verification
The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay of both rounds; `success` = 1 iff the match is valid and decided (played out, or won on the opponent's clock or
start); the winner is `A_won` / `B_won` (exactly one in a valid match). `reward.json` also reports both totals and
per-hole scores, the play-off holes (`tiebreaks`), whether the clock decided (`clock_decided`), `official_config`,
`technical_failure`, `clock_forfeit` and `start_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | WMF Rulebook 2.3, Worldwide international sport rules (World Minigolf Sport Federation), https://gov.minigolfsport.com/rules/2_3.pdf; secondary: R&A/USGA Rules of Golf 2023, https://www.randa.org/rog; scoring as WMF 9.1, order of play as WMF 11.2, lowest total wins (WMF 9.2), a tie goes to a sudden-death play-off (WMF 9.3), at most 4 holes, then more chess-clock time left wins |
| Deviations | greens enclosed by walls: no border line, no out of bounds (WMF 2.7, 8); a chess clock instead of the per-stroke time limit (WMF 11.3); the starter alternates from hole to hole instead of the honour (R&A 6.4b), and the first play-off hole continues the alternation instead of a coin flip (WMF 9.3); the play-off stops after 4 holes, then the chess clock decides (WMF 9.3 continues until there is a difference) |
| Parameters | `DUEL_SEED` (default 20260928), `FIRST_PLAYER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task golf-putting-duel-program-standard --a opus\|astra\|oracle --b ... [--seed N] [--first A\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / clock | 30 minutes to start after the first player; one 60-minute chess clock per player |
| Generator | `scripts/olympiad/generate.py` |
