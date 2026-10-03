# archery-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (bow release primitive)` |
| Family / instance | `archery_duel` |
| Oracle | `full` — solution/: the reference archer (camera images and the documented physics) on either seat; oracle against oracle plays valid matches with either first player |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents shoot the same round (4 ends x 3 arrows at 50, 70, 70, 90 m) on identical lanes: the same wind and the
same release scatter for the n-th arrow of either player. In each end one player shoots its 3 arrows, then the other;
the higher total wins, a tie goes to a shoot-off. Each may write a program that reads the windsocks and the target in
the camera images and computes and sends its shots, and reviews after every arrow.

## Difficulty
Set at run time: seed (`DUEL_SEED`: the winds and the scatter draws) and first player (`FIRST_PLAYER`: it shoots
first in ends 1 and 3, the other in ends 2 and 4). Official configurations: seeds [1, 2, 3], each with both
first players (play both orders for a fair comparison).

## Reference solution
`solution/` holds the reference archer (`archery_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid (seat B's reference aims 3 mm left of seat A's, so that two references cannot tie forever).

## Verification
The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`
(shoot-offs repeat until the tie is broken). `reward.json` also reports both totals, the shoot-off, the clocks, `seed` and
`official_config`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task archery-duel-program-standard --a opus\|astra\|oracle --b ... [--seed N] [--first A\|B]` |
| Format | 4 ends x 3 arrows each; per end one player shoots 3 arrows, then the other (FIRST_PLAYER first in ends 1 and 3); higher total wins; tie: shoot-off arrows at 70 m (WA 12.5.2.2), one each, score then distance to the centre, repeated until the tie is broken; cumulative scoring as in compound match play (WA 12.1.4.3) |
| Turns and clocks | An action or review out of turn: HTTP 409; images only on one's own turn. One chess clock of 60 minutes per player, on its own turn (arrows and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
| Rules | World Archery Rulebook, Book 3: Target Archery (version 2026-03-13), https://extranet.worldarchery.sport/documents/index.php/?doc=7626&inline=1. Deviations: (1) A short custom round (4 ends x 3 arrows at 50, 70, 70, 90 m) instead of a standard match round; no practice ends. (2) Each player shoots its 3 arrows of an end in a block, not alternating arrow by arrow (WA 11.1.4.1, 11.2.3.2). (3) The end order is fixed (the first player starts ends 1 and 3, the other ends 2 and 4) instead of the trailing archer starting the next end (WA 11.1.4.1). (4) The shoot-off is shot at 70 m. (5) The arrows are shot by a release primitive with a stated scatter; time is a chess clock instead of end and arrow time limits (WA 11.2). |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |
