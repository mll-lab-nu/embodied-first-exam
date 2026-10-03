# darts-501-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (dart release mechanism)` |
| Family / instance | `darts_501` |
| Oracle | `full` — solution/: a reference player from the camera images and the documented physics (it measures its darts in the board close-up and fits the drag); offline it wins all 12 official configurations |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Best of 3 legs of 501 double-out (3 darts per visit, bust rule; WDF rules) against a deterministic scripted thrower
that throws first in legs 1 and 3 (the agent in leg 2) and aims with the optimal-aim policy for its own scatter (Tibshirani et al. 2011, extended to minimum expected
visits to check out). A regulation board in a MuJoCo scene (osmesa rendering); the dart flies under gravity and
quadratic drag whose constant is not given. Each dart is a release command (`game throw YAW PITCH SPEED`) with
published seeded scatter; the agent sees camera images only (thrower's view, side view with its last dart's path,
board close-up) and hears the caller's calls. It may write a program that measures its darts in the images and computes
and sends its throws; it stays in the loop and reviews after every dart. The prompt follows the general turn-based
program-play structure (`scripts/olympiad/turn_prompt.py`) with darts' sections (`scripts/olympiad/darts/darts_prompt.py`).

## Difficulty
Set at run time: opponent level 1-4 (`RCB_LEVEL`; its execution scatter shrinks from about 3 times the agent's
at L1 to about 1.1 times at L4) and seed (`RCB_SEED`: the drag constant and both throwers' scatter draws). Time: a
60-minute chess clock on the agent's turn. Official configurations: levels with seeds {1: [5011, 5012, 5013], 2: [5021, 5022, 5023], 3: [5031, 5032, 5033], 4: [5041, 5042, 5043]}.

## Reference solution
`solution/solve.sh` runs a reference player (`solution/darts_ref.py`) that uses only the camera images and the
documented physics: it finds each of its darts in the board close-up by its flight colour, refits the drag constant
from its landing errors, and aims with the optimal-aim table for its own scatter (`solution/policy_player.json`).

## Verification
The `sim` service records the match; a fresh process replays the throws and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic
replay; no simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `official_config`,
`valid_trial`, `technical_failure`, `clock_forfeit`, both players' legs and remaining scores and the agent's three-dart
average.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (1-4, default 1), `RCB_SEED` (default 5011) |
| Run | `scripts/olympiad/run_single.sh --task darts-501-program-standard --agent opus\|astra\|oracle\|nop --level L --seed N` |
| Clock | 60 minutes from `game start`, on the agent's turn only (reviews included); out of time = the match is lost |
| Rules | WDF Playing and Tournament Rules, 20th revised edition (2018), https://dartswdf.com/storage/uploads/fb05b306-c92c-4f08-b512-affb092a1b3d/2018-02-28_WDF_Playing_and_Tournament_Rules_rev20.pdf. Deviations: (1) The darts are thrown by a release mechanism with a stated scatter, not by hand, and there are no practice darts (WDF 1.02, 13.01). (2) Darts always stick where the point reaches the board: no bounce-outs, fall-outs or wire deflections (WDF 1.05-1.06, 3.02-3.03). (3) The throw order is fixed (the opponent first in legs 1 and 3) instead of a throw for the bull (WDF 12.01-12.03). (4) The 30-visit cap per leg, with the lower remaining score and then the chess clocks deciding, is a cost limit; the rules play on until someone checks out. |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
