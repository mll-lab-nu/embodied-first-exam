# darts-duel-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (dart release mechanism)` |
| Family / instance | `darts_duel` |
| Oracle | `full` — solution/: the reference player (camera images and the documented physics) on either seat; oracle against oracle plays valid matches with either first player |
| Agent time budget | 10800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents throw at one regulation board with identical release mechanisms (the same drag and the same scatter
draws): best of 3 legs of 501 double-out, alternate visits of 3 darts. Each may write a program that measures its
darts in the camera images and computes and sends its throws, and reviews after every dart.

## Difficulty
Set at run time: seed (`DUEL_SEED`: the drag constant and the scatter draws) and first player (`FIRST_PLAYER`: it
throws first in legs 1 and 3, the other in leg 2). Official configurations: seeds [1, 2, 3], each with
both first players (play both orders for a fair comparison).

## Reference solution
`solution/` holds the reference player (`darts_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid.

## Verification
The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`.
`reward.json` also reports both seats' legs, remaining scores and clocks, `clock_forfeit`, `seed` and
`official_config`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task darts-duel-program-standard --a opus\|astra\|oracle --b ... [--seed N] [--first A\|B]` |
| Format | Best of 3 legs of 501 double-out; visits of 3 darts alternate; FIRST_PLAYER throws first in legs 1 and 3; visit cap 30 each per leg (lower remaining wins; tie: the second thrower) |
| Turns and clocks | An action or review out of turn: HTTP 409. One chess clock of 60 minutes per player, running on its own turn (its darts and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
| Rules | WDF Playing and Tournament Rules, 20th revised edition (2018), https://dartswdf.com/storage/uploads/fb05b306-c92c-4f08-b512-affb092a1b3d/2018-02-28_WDF_Playing_and_Tournament_Rules_rev20.pdf. Deviations: (1) The darts are thrown by a release mechanism with a stated scatter, not by hand, and there are no practice darts (WDF 1.02, 13.01). (2) Darts always stick where the point reaches the board: no bounce-outs, fall-outs or wire deflections (WDF 1.05-1.06, 3.02-3.03). (3) The throw order is fixed by the configuration instead of a throw for the bull; both orders are played (WDF 12.01-12.03). (4) The 30-visit cap per leg, with the lower remaining score and then the chess clocks deciding, is a cost limit; the rules play on until someone checks out. |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |
