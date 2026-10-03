# basketball-shootout-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-turn/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `basketball_shootout` |
| Oracle | `full` — solution/: a reference shooter from the camera images and the documented physics (it locates the rim in the zoom camera and solves the flight); it makes 6, 7 and 4 of 10 on the official seeds 7, 17, 27 (success line 6) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A simulated Franka Panda launcher on a 1 m pedestal takes 10 shots, two from each of five spots (mid-range to beyond the
three-point line; 1 point per make; NBA court markings), with a static defender between it and the hoop (MuJoCo, osmesa rendering; ball with drag and
Magnus force; rim, backboard and floor contacts). Each shot is `game shoot ANGLE SPEED SPIN YAW`; the agent sees
camera images only (two cameras on the shooter, two on the court; no hoop, ball or spot coordinates) and a picture
strip of every shot. It may write a program that finds the hoop in the images and computes and sends its shots; it
stays in the loop and reviews after every shot. Success: at least 6 makes of 10 (as in the old task); the
makes are always reported and more is better. Unlike the old task, thinking costs no simulated time: the defender
stands still and there is no shot clock (program play times the agent with the chess clock instead). The prompt
follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`, played alone) with
basketball's sections (`scripts/olympiad/basketball/basketball_prompt.py`).

## Difficulty
Set at run time: the seed (`RCB_SEED`: the five spots, the shooter's heading offsets of 4-9 degrees and the
release scatter). Makes need the speed right to 1-2 % and the direction to about 1 degree, so the hoop must be located
precisely from the images. Time: a 60-minute chess clock. Official configurations: seeds [7, 17, 27].

## Reference solution
`solution/solve.sh` runs a reference shooter (`solution/bb_ref.py`) that uses only the camera images and the
documented physics: it finds the rim in the zoom camera, turns its centre into the hoop's bearing and distance with
the camera pose from `game spec`, solves the documented flight for the release speed at 54 degrees, and corrects the
second shot from a spot after a miss.

## Verification
The `sim` service records the shootout; a fresh process replays the shots and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the shootout is valid (deterministic replay;
no simulator, model-API or metering failure), complete and has at least 6 makes. `reward.json` also reports
`made`, the result counts, `seed`, `official_config`, `valid_trial`, `technical_failure` and `clock_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_SEED` (default 7) |
| Run | `scripts/olympiad/run_single.sh --task basketball-shootout-program-standard --agent opus\|astra\|oracle\|nop --level 1 --seed N` (no levels: `--level 1`) |
| Clock | 60 minutes from `game start` (reviews included); out of time = the round ends, the shots not taken are misses |
| Rules | FIBA Official Basketball Rules 2024 (Art. 16, goal), https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2024-v10a.pdf; closest standard contest: FIBA 3x3 Shoot-out Contest, https://fiba3x3.com/en/rules.html. Deviations: (1) A shooting contest: 10 shots from five spots, instead of a game. (2) Every make counts 1, from any spot, instead of 2 or 3 points by the release area (FIBA Art. 16.2.1). (3) NBA court markings and equipment sizes (FIBA Art. 2 uses a 6.75 m three-point arc and a 1.80 m backboard). (4) A static defender with its hands up, and a ball that touches it first does not count, instead of live defence. (5) The shots are thrown by a launcher with a stated scatter; time is a chess clock instead of a shot clock. |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
