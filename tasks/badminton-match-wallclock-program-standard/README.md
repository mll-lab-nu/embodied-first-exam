# badminton-match-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_match` |
| Oracle | `full` — solution/: the privileged reference player (true shuttle state through the oracle-only endpoint, ordinary acts); checked valid at L1-L2, x1-x20 |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
A simulated Franka Panda arm on a sliding base, holding a badminton racket, plays a singles match (first to 5 points, two-point lead from 4-4, at most 7,
rally scoring) against a scripted computer opponent, in real time slowed by a factor S. The shuttle is a point mass
with quadratic drag and no bounce. The agent sees the shuttle only through two cameras and may write a player program
that observes and acts on its own; it may fix and restart the program at any time and reviews after every point. The
prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with badminton's sections
(`scripts/olympiad/badminton/badminton_prompt.py`).

## Difficulty
Set at run time: opponent level 1-2 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {1: [101, 111, 121], 2: [202, 212, 222]}, slowdowns [1, 2, 5, 10, 20].

## Reference solution
`solution/solve.sh` runs the privileged reference player: with `RCB_PLAYER_MODE=oracle` (set by the runner for
`oracle`/`nop` only) the service exposes `POST /oracle` with the true shuttle state and a reference decision computed
on an exact copy of the match (`environment/sim/oracle_ref.py`); the decision is sent as an ordinary `act` and pays
every wall-clock cost. In model mode the endpoint answers 403.

## Verification
The `sim` service records the match and replays it in a fresh process from the logged acts; a separate verifier
(`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic replay; no
simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `slowdown`, `official_config`,
`valid_trial` and `technical_failure`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | [BWF Laws of Badminton (BWF Statutes, Section 4.1, in force 26 April 2025, version 5.0)](https://extranet.bwf.sport/docs/document-system/81/1466/1470/Section%204.1%20-%20Laws%20of%20Badminton%20-%2026%20April%202025%20V5.0%20(2)%20.pdf). Deviations: the opponent serves every point (Law 10.3); one game to 5 points, a two-point lead from 4-4, at most 7 (Law 7: best of three to 21, cap 30); serves from the server's right or left service court by the server's score (10.1.1) into the diagonal court (9.1; outside it: a fault, the receiver's point, 13.1); net top 1.524 m (1.10); base 6 m/s, 20 m/s^2; point-mass shuttle: a crossing of the net plane below the top is a fault, net touch / reaching over the net (13.4) not judged; robots back home before every serve; 300 hits in the match end it after that point (the leader wins, if level the winner of the last point: no draws). The single-player task and the duel play by the same rules; only who serves differs |
| Parameters | `RCB_LEVEL` (1-2, default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Run | `scripts/olympiad/run_single.sh --task badminton-match-wallclock-program-standard --agent opus\|astra\|oracle\|nop --level L --slowdown S --seed N` |
| Act lead | an act takes effect `timing.act_lead_steps` = ceil(0.4 s / (0.01 S)) control steps after it arrives (the stroke planner's time) |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |
