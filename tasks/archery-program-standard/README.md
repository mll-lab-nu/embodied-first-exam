# archery-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `none (bow release primitive)` |
| Family / instance | `archery_target` |
| Oracle | `full` — solution/: a reference archer from the camera images and the documented physics (it reads the windsocks and solves the ballistics); offline it scores 115, 112 and 112 on the official seeds (success line 110) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A target-archery round (World Archery rules, a short custom round) of 4 ends x 3 arrows at a World Archery 122 cm 10-ring face (50, 70, 70, 90 m) in a seeded,
gusty crosswind and headwind (MuJoCo scene, osmesa rendering; deterministic point-mass arrow with quadratic drag on the
air-relative velocity, Cd 1.5 per Miyazaki et al. 2013). Each arrow is `game shoot ELEV_DEG AZIM_DEG DRAW`; the agent
sees camera images only (archer's view with the windsocks, scope view, side view of a windsock, close-up of the face;
no coordinates, no wind numbers). It may write a program that reads the windsocks and the target in the images and
computes and sends its shots; it stays in the loop and reviews after every arrow. Success: a complete round with a total
of at least 110 of 120 (as in the old task); the total is always reported and higher is better. The prompt
follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`, played alone) with archery's
sections (`scripts/olympiad/archery/archery_prompt.py`).

## Difficulty
Set at run time: the seed (`RCB_SEED`: the wind of every arrow and the release scatter). Reading the wind to about
1 m/s is needed for the success line: offline, an archer that knows the true wind scores about 114, one that reads it
within 1 m/s about 111, and one that ignores it about 92. Time: a 60-minute chess clock. Official configurations:
seeds [20260929, 2, 3].

## Reference solution
`solution/solve.sh` runs a reference archer (`solution/archery_ref.py`) that uses only the camera images and the
documented physics: it fits the wind to where the windsocks' orange stripes appear in the archer's and side views, and
solves the ballistics for the gold centre at full draw.

## Verification
The `sim` service records the round; a fresh process replays the shots and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the round is valid (deterministic replay; no
simulator, model-API or metering failure), complete and scores at least 110. `reward.json` also reports
`total`, the end scores, `seed`, `official_config`, `valid_trial`, `technical_failure` and `clock_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_SEED` (default 20260929) |
| Run | `scripts/olympiad/run_single.sh --task archery-program-standard --agent opus\|astra\|oracle\|nop --level 1 --seed N` (no levels: `--level 1`) |
| Clock | 60 minutes from `game start` (reviews included); out of time = the round ends, the arrows not shot score M |
| Rules | World Archery Rulebook, Book 3: Target Archery (version 2026-03-13), https://extranet.worldarchery.sport/documents/index.php/?doc=7626&inline=1. Deviations: (1) A short custom round (12 arrows at 50-90 m) instead of a standard round; no practice ends. (2) The arrows are shot by a release primitive with a stated scatter; time is a chess clock instead of 2 minutes per 3-arrow end (WA 11.2). |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
