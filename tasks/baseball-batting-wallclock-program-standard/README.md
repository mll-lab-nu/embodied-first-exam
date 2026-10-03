# baseball-batting-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `swing-rig` |
| Family / instance | `baseball_batting` |
| Oracle | `full` — solution/: a scripted camera-only batter; checked valid at L1-L4 and x1-x20; passes the 4-base line at x2-x20 (5 home runs typical), at x1 its observations arrive too late to swing |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A simulated swing rig holding a wooden bat (robot `swing-rig`, not a Franka) bats through 5 plate appearances
against a scripted computer pitcher, in real time slowed by a factor S, and must collect at least 4 bases (walk or
single 1, double 2, home run 4). The agent sees the ball only through two cameras and may write a batting program that
observes and swings on its own; it may fix and restart the program at any time and reviews after every pitch. The
prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with baseball's sections
(`scripts/olympiad/baseball/baseball_prompt.py`).

## Difficulty
Set at run time: pitcher level 1-4 (`RCB_LEVEL`: L1 fastballs only, 34-36 m/s, mostly in the zone; L2 adds
changeups and curveballs and more balls; L3 faster fastballs, sliders, the edges of the zone; L4 the hardest fastballs,
overlapping speed bands, pitches chosen by the count) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {1: [301, 311, 321], 2: [302, 312, 322], 3: [303, 313, 323], 4: [304, 314, 324]}, slowdowns [1, 2, 5, 10, 20].

## Reference solution
`solution/solve.sh` runs a scripted batter that uses only the camera images, the spec and the documented
ball and rig models (`solution/bat_player.py`: ball detection against a windup background, a fit of the release
velocity for each documented pitch type's spin, the swing geometry for a line drive; it takes pitches it predicts out
of the zone).

## Verification
The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent collects at least 4 bases in a valid game (deterministic
replay; no simulator, model-API or metering failure). `reward.json` also reports `bases`, `level`, `seed`, `slowdown`,
`official_config`, `valid_trial` and `technical_failure`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 301) |
| Run | `scripts/olympiad/run_single.sh --task baseball-batting-wallclock-program-standard --agent opus\|astra\|oracle\|nop --level L --slowdown S --seed N` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
| Rulebook | MLB *Official Baseball Rules*, 2026 edition: https://mktg.mlbstatic.com/mlb/official-information/2026-official-baseball-rules.pdf |
| Field | as in 2.01: bases 90 ft (27.43 m) apart, the pitch released about 1.4 m in front of the rubber (18.44 m) |
| Count and zone | strike, ball, foul, strikeout, walk as in the Definitions of Terms, 5.05(b), 5.09(a) |
| Deviations | no base runners, runs or innings: each plate appearance scores the bases the batter reaches, no triples (5.05, 5.06); no batter's body, so no hit by pitch (5.05(b)(2)); fouls are never caught and there are no foul tips (5.09(a)(1), "Foul Tip"); fair/foul at the first landing point also for short balls ("Fair Ball"); the strike zone judged in one plane at fixed heights ("Strike Zone"); a uniform 100 m, 3 m high fence (2.01 Note: 325 ft at the lines, 400 ft to centre); fixed fielders without errors; a plate appearance reaching 15 pitches is an out (no limit in MLB) |
