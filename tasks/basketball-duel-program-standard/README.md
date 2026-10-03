# basketball-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `basketball_duel` |
| Oracle | `full` — solution/: the reference shooter (camera images and the documented physics) on either seat; oracle against oracle plays valid matches with either first player |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents each control a simulated Franka Panda launcher on identical courts: the same five spots and headings,
the same release scatter for the n-th shot of either player. Five rounds, one per spot: one player takes its 2 shots,
then the other; the most makes wins, a tie goes to extra shots. Each may write a program that finds the hoop in the
camera images and computes and sends its shots, and reviews after every shot.

## Difficulty
Set at run time: seed (`DUEL_SEED`: the spots, headings and scatter draws) and first player (`FIRST_PLAYER`: it
shoots first in rounds 1, 3 and 5). Official configurations: seeds [1, 2, 3], each with both first players
(play both orders for a fair comparison).

## Reference solution
`solution/` holds the reference shooter (`bb_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid (seat B's reference shoots 1 % faster and 0.3 degrees left of seat A's, so that two references meeting the same scatter do not tie every extra pair).

## Verification
The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`
(exactly one of them; a match level after 30 extra pairs goes to the player with more chess-clock time left). `reward.json` also reports both players' makes, the extra pairs, the clocks, `seed` and
`official_config`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task basketball-duel-program-standard --a opus\|astra\|oracle --b ... [--seed N] [--first A\|B]` |
| Format | Five rounds, one per spot; per round one player takes 2 shots, then the other (FIRST_PLAYER first in rounds 1, 3, 5); most makes wins; tie: pairs of extra shots (one each, FIRST_PLAYER first, spots 1, 2, ... 5, 1, ...) until one pair differs; safety cap of 30 tied pairs, then the player with more chess-clock time left wins (no draws) |
| Turns and clocks | An action or review out of turn: HTTP 409; images only on one's own turn. One chess clock of 60 minutes per player, on its own turn (shots and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
| Rules | FIBA Official Basketball Rules 2024 (Art. 16, goal), https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2024-v10a.pdf; closest standard contest: FIBA 3x3 Shoot-out Contest, https://fiba3x3.com/en/rules.html. Deviations: (1) A shooting contest: two players, 2 shots each from five spots in alternating rounds, then extra pairs of shots on a tie, with a safety cap of 30 pairs decided by the chess clocks, instead of a game. (2) Every make counts 1, from any spot, instead of 2 or 3 points by the release area (FIBA Art. 16.2.1). (3) NBA court markings and equipment sizes (FIBA Art. 2 uses a 6.75 m three-point arc and a 1.80 m backboard). (4) A static defender with its hands up, and a ball that touches it first does not count, instead of live defence. (5) The shots are thrown by a launcher with a stated scatter; time is a chess clock instead of a shot clock. |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |
